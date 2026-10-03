package syncer

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

func TestRunRedownloadsAFileMissingFromDisk(t *testing.T) {
	content := []byte("hello")
	requests := 0
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		requests++
		response.WriteHeader(http.StatusOK)
		_, _ = response.Write(content)
	}))
	defer server.Close()
	client, err := moodle.NewClient(server.URL, "token")
	if err != nil {
		t.Fatal(err)
	}
	resource := moodle.Resource{
		ID: "resource-1", CourseID: 7, CourseName: "Materia", ModuleName: "Unidad",
		Name: "guia.txt", URL: server.URL + "/webservice/pluginfile.php/1/guia.txt",
		Type: moodle.ResourceFile, Size: int64(len(content)), Accessible: true,
	}
	catalog := moodle.Catalog{Resources: []moodle.Resource{resource}}
	directory := t.TempDir()
	options := Options{OutputPath: directory, Modes: map[int]Mode{7: {Name: "update", ScanExisting: true}}, Workers: 1}

	first, err := Run(context.Background(), client, catalog, options)
	if err != nil || first.Downloaded != 1 {
		t.Fatalf("first run: report=%#v err=%v", first, err)
	}
	second, err := Run(context.Background(), client, catalog, options)
	if err != nil || second.Unchanged != 1 || requests != 1 {
		t.Fatalf("second run: report=%#v requests=%d err=%v", second, requests, err)
	}
	path := filepath.Join(directory, "Materia", "Unidad", "guia.txt")
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	third, err := Run(context.Background(), client, catalog, options)
	if err != nil || third.Downloaded != 1 || requests != 2 {
		t.Fatalf("third run: report=%#v requests=%d err=%v", third, requests, err)
	}
}

func TestRunDoesNotMarkFailedDownloadAsComplete(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		http.Error(response, "missing", http.StatusNotFound)
	}))
	defer server.Close()
	client, _ := moodle.NewClient(server.URL, "token")
	resource := moodle.Resource{
		ID: "failed", CourseID: 8, CourseName: "Materia", ModuleName: "Unidad",
		Name: "missing.pdf", URL: server.URL + "/webservice/pluginfile.php/1/missing.pdf",
		Type: moodle.ResourcePDF, Size: 10, Accessible: true,
	}
	directory := t.TempDir()
	report, err := Run(context.Background(), client, moodle.Catalog{Resources: []moodle.Resource{resource}}, Options{OutputPath: directory, Workers: 1})
	if err == nil || report.Failed != 1 {
		t.Fatalf("report=%#v err=%v", report, err)
	}
	manifest, err := loadManifest(filepath.Join(directory, "config", "manifest.json"))
	if err != nil {
		t.Fatal(err)
	}
	module := manifest.module(8, "Materia", "Unidad", false)
	if module != nil && module.Resources[resource.ID] != nil {
		t.Fatal("failed resource was incorrectly marked as complete")
	}
}

func TestPlanDestinationsPreservesFoldersAndResolvesCollisions(t *testing.T) {
	resources := []moodle.Resource{
		{ID: "aaaaaaaa1", CourseName: "Materia", ModuleName: "Unidad", Subfolder: "Pila", Name: "nodo.h"},
		{ID: "bbbbbbbb2", CourseName: "Materia", ModuleName: "Unidad", Subfolder: "Pila", Name: "nodo.h"},
		{ID: "cccccccc3", CourseName: "Materia", ModuleName: "Unidad", Subfolder: "Cola", Name: "nodo.h"},
	}
	paths := planDestinations(resources, newManifest())
	if filepath.Dir(paths["aaaaaaaa1"]) != filepath.Join("Materia", "Unidad", "Pila") {
		t.Fatalf("nested path lost: %s", paths["aaaaaaaa1"])
	}
	if paths["aaaaaaaa1"] == paths["bbbbbbbb2"] {
		t.Fatal("colliding resources received the same path")
	}
	if filepath.Dir(paths["cccccccc3"]) != filepath.Join("Materia", "Unidad", "Cola") {
		t.Fatalf("second nested path lost: %s", paths["cccccccc3"])
	}
}

func TestRunSavesExternalLinkWithoutDroppingItsToken(t *testing.T) {
	client, _ := moodle.NewClient("https://moodle.example", "moodle-token")
	resource := moodle.Resource{
		ID: "link", CourseID: 9, CourseName: "Materia", ModuleName: "Unidad",
		Name: "Documentación", URL: "https://example.com/share?token=external-token",
		Type: moodle.ResourceLink, Accessible: true,
	}
	directory := t.TempDir()
	report, err := Run(
		context.Background(), client, moodle.Catalog{Resources: []moodle.Resource{resource}},
		Options{OutputPath: directory, Workers: 1},
	)
	if err != nil || report.LinksSaved != 1 {
		t.Fatalf("report=%#v err=%v", report, err)
	}
	content, err := os.ReadFile(filepath.Join(directory, "Materia", "Unidad", "Documentación.url"))
	if err != nil {
		t.Fatal(err)
	}
	if string(content) != "[InternetShortcut]\nURL=https://example.com/share?token=external-token\n" {
		t.Fatalf("unexpected shortcut: %q", content)
	}
}

func TestRunReportsCoursesThatCouldNotBeAnalysed(t *testing.T) {
	client, _ := moodle.NewClient("https://moodle.example", "token")
	catalog := moodle.Catalog{Diagnostics: moodle.Diagnostics{
		CourseErrors: []moodle.CourseError{{Course: "Rota", Error: "HTTP 403"}},
	}}
	report, err := Run(context.Background(), client, catalog, Options{OutputPath: t.TempDir(), Workers: 1})
	if err == nil {
		t.Fatal("a course that could not be analysed must make the sync partial")
	}
	if report.Failed != 1 || len(report.Failures) != 1 || report.Failures[0].Course != "Rota" {
		t.Fatalf("report=%#v", report)
	}
}

// Regression: v0.1.6 saved every re-download as name_1.ext, name_2.ext...
// whenever a module changed or a full download was forced.
func TestRerunsNeverCreateDuplicateCopies(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		_, _ = response.Write([]byte("%PDF"))
	}))
	defer server.Close()
	client, _ := moodle.NewClient(server.URL, "token")
	file := func(id, name string) moodle.Resource {
		return moodle.Resource{
			ID: id, CourseID: 7, CourseName: "Materia", ModuleName: "Unidad 1", Name: name,
			URL: server.URL + "/webservice/pluginfile.php/1/" + name, Type: moodle.ResourcePDF,
			Size: 4, Accessible: true,
		}
	}
	directory := t.TempDir()
	run := func(mode Mode, resources ...moodle.Resource) {
		t.Helper()
		_, err := Run(context.Background(), client, moodle.Catalog{Resources: resources},
			Options{OutputPath: directory, Modes: map[int]Mode{7: mode}, Workers: 2})
		if err != nil {
			t.Fatal(err)
		}
	}
	update := Mode{Name: "update", ScanExisting: true}
	run(update, file("a", "Unidad1.pdf"))
	run(update, file("a", "Unidad1.pdf"), file("b", "Unidad1-practico.pdf"))
	run(Mode{Name: "full", ScanExisting: true}, file("a", "Unidad1.pdf"), file("b", "Unidad1-practico.pdf"))
	run(Mode{Name: "full", ScanExisting: true}, file("a", "Unidad1.pdf"), file("b", "Unidad1-practico.pdf"))

	entries, err := os.ReadDir(filepath.Join(directory, "Materia", "Unidad 1"))
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, entry := range entries {
		names = append(names, entry.Name())
	}
	if len(names) != 2 {
		t.Fatalf("expected exactly the 2 Moodle files, got %v", names)
	}
}

func TestCollidingFilesKeepTheirPathsWhenCatalogOrderChanges(t *testing.T) {
	contents := map[string]string{"/webservice/pluginfile.php/1/a": "AAAA", "/webservice/pluginfile.php/2/b": "BBBB"}
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		_, _ = response.Write([]byte(contents[request.URL.Path]))
	}))
	defer server.Close()
	client, _ := moodle.NewClient(server.URL, "token")
	file := func(id, path string, modified int64) moodle.Resource {
		return moodle.Resource{
			ID: id, CourseID: 7, CourseName: "Materia", ModuleName: "Unidad", Name: "apunte.pdf",
			URL: server.URL + path, Type: moodle.ResourcePDF, Size: 4, Modified: modified, Accessible: true,
		}
	}
	directory := t.TempDir()
	run := func(resources ...moodle.Resource) {
		t.Helper()
		_, err := Run(context.Background(), client, moodle.Catalog{Resources: resources},
			Options{OutputPath: directory, Modes: map[int]Mode{7: {Name: "update", ScanExisting: true}}, Workers: 1})
		if err != nil {
			t.Fatal(err)
		}
	}
	run(file("aaaaaaaa1", "/webservice/pluginfile.php/1/a", 1), file("bbbbbbbb2", "/webservice/pluginfile.php/2/b", 1))
	contents["/webservice/pluginfile.php/2/b"] = "bbbb"
	run(file("bbbbbbbb2", "/webservice/pluginfile.php/2/b", 2), file("aaaaaaaa1", "/webservice/pluginfile.php/1/a", 1))

	entries, err := os.ReadDir(filepath.Join(directory, "Materia", "Unidad"))
	if err != nil {
		t.Fatal(err)
	}
	found := map[string]bool{}
	for _, entry := range entries {
		data, _ := os.ReadFile(filepath.Join(directory, "Materia", "Unidad", entry.Name()))
		found[string(data)] = true
	}
	if len(entries) != 2 || !found["AAAA"] || !found["bbbb"] {
		t.Fatalf("a colliding file was overwritten: %d files, contents %v", len(entries), found)
	}
}

func TestPlanDestinationsDoesNotDependOnCatalogOrder(t *testing.T) {
	a := moodle.Resource{ID: "aaaaaaaa1", CourseName: "Materia", ModuleName: "Unidad", Name: "nodo.h"}
	b := moodle.Resource{ID: "bbbbbbbb2", CourseName: "Materia", ModuleName: "Unidad", Name: "nodo.h"}
	forward := planDestinations([]moodle.Resource{a, b}, newManifest())
	backward := planDestinations([]moodle.Resource{b, a}, newManifest())
	if forward["aaaaaaaa1"] != backward["aaaaaaaa1"] || forward["bbbbbbbb2"] != backward["bbbbbbbb2"] {
		t.Fatalf("paths depend on order: %v vs %v", forward, backward)
	}
}

func TestDownloadErrorsNeverExposeTheToken(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {}))
	base := server.URL
	server.Close()
	client, _ := moodle.NewClient(base, "secret-moodle-token")
	resource := moodle.Resource{
		ID: "r", CourseID: 7, CourseName: "Materia", ModuleName: "Unidad", Name: "guia.pdf",
		URL: base + "/webservice/pluginfile.php/1/guia.pdf", Type: moodle.ResourcePDF, Accessible: true,
	}
	_, err := downloadFile(context.Background(), client, resource, filepath.Join(t.TempDir(), "guia.pdf"))
	if err == nil {
		t.Fatal("expected a connection error")
	}
	if strings.Contains(err.Error(), "secret-moodle-token") {
		t.Fatalf("token leaked into error: %v", err)
	}
}

func TestCancelledRunKeepsFinishedFilesAndReportsNoFailures(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if strings.HasSuffix(request.URL.Path, "/lento.pdf") {
			<-request.Context().Done()
			return
		}
		_, _ = response.Write([]byte("%PDF"))
	}))
	defer server.Close()
	client, _ := moodle.NewClient(server.URL, "token")
	file := func(id, name string) moodle.Resource {
		return moodle.Resource{
			ID: id, CourseID: 7, CourseName: "Materia", ModuleName: "Unidad", Name: name,
			URL: server.URL + "/webservice/pluginfile.php/1/" + name, Type: moodle.ResourcePDF, Size: 4, Accessible: true,
		}
	}
	resources := []moodle.Resource{file("a", "rapido.pdf"), file("b", "lento.pdf")}
	for index := 0; index < 20; index++ {
		resources = append(resources, file(fmt.Sprintf("z%02d", index), fmt.Sprintf("pendiente%02d.pdf", index)))
	}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	directory := t.TempDir()
	report, err := Run(ctx, client, moodle.Catalog{Resources: resources}, Options{
		OutputPath: directory, Workers: 2,
		Progress: func(message string) {
			if message == "✓ rapido.pdf" {
				cancel()
			}
		},
	})
	if !errors.Is(err, context.Canceled) {
		t.Fatalf("expected cancellation error, got %v", err)
	}
	if !report.Cancelled || report.Failed != 0 || report.Downloaded != 1 {
		t.Fatalf("unexpected report: %#v", report)
	}
	manifest, _ := loadManifest(filepath.Join(directory, "config", "manifest.json"))
	module := manifest.module(7, "Materia", "Unidad", false)
	if module == nil || module.Resources["a"] == nil {
		t.Fatal("the file finished before cancelling was not recorded")
	}
}
