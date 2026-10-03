package gdrive

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

const (
	presentationMIME = "application/vnd.google-apps.presentation"
	formMIME         = "application/vnd.google-apps.form"
)

func driveLink(course int, module, name, url string) moodle.Resource {
	return moodle.Resource{
		ID: "link-" + name, CourseID: course, CourseName: "Sistemas", ModuleName: module,
		Name: name, URL: url, Type: moodle.ResourceGoogle, Source: "label", Accessible: true,
	}
}

func catalogWith(resources ...moodle.Resource) moodle.Catalog {
	return moodle.Catalog{Resources: resources, Diagnostics: moodle.Diagnostics{ResourcesBySource: map[string]int{}}}
}

func driveResources(catalog moodle.Catalog) map[string]moodle.Resource {
	found := map[string]moodle.Resource{}
	for _, resource := range catalog.Resources {
		if resource.Source == "google_drive" {
			found[resource.Subfolder+"|"+resource.Name] = resource
		}
	}
	return found
}

func keys(found map[string]moodle.Resource) []string {
	list := make([]string, 0, len(found))
	for key := range found {
		list = append(list, key)
	}
	sort.Strings(list)
	return list
}

// cátedra: a public folder with a subfolder, native files and a form.
func catedraDrive(t *testing.T) *fakeDrive {
	return newFakeDrive(t,
		&fakeFile{ID: "ROOT", Name: "Cátedra A", MimeType: folderMIME, Public: true},
		&fakeFile{ID: "f1", Name: "programa.pdf", MimeType: "application/pdf", Parent: "ROOT", Content: "%PDF", Public: true, Modified: "2026-09-02T10:00:00Z"},
		&fakeFile{ID: "f2", Name: "Clase 1", MimeType: presentationMIME, Parent: "ROOT", Public: true},
		&fakeFile{ID: "f3", Name: "Notas", MimeType: sheetMIME, Parent: "ROOT", Public: true},
		&fakeFile{ID: "f4", Name: "Encuesta", MimeType: formMIME, Parent: "ROOT", Public: true},
		&fakeFile{ID: "SUB", Name: "Unidad 2", MimeType: folderMIME, Parent: "ROOT", Public: true},
		&fakeFile{ID: "f5", Name: "tp.docx", MimeType: "application/msword", Parent: "SUB", Content: "doc", Public: true},
		&fakeFile{ID: "f6", Name: "viejo.pdf", MimeType: "application/pdf", Parent: "SUB", Trashed: true, Public: true},
	)
}

const catedraURL = "https://drive.google.com/drive/folders/ROOT?usp=sharing"

func TestExpandIncludedFolderAddsEveryFileUnderTheLink(t *testing.T) {
	catedraDrive(t)
	client := newTestClient(t, "")
	link := driveLink(7, "Unidad 1", "Material cátedra", catedraURL)
	result, err := Expand(context.Background(), client, catalogWith(link), ExpandOptions{
		Selection: Selection{Rules: map[string]string{"ROOT": RuleInclude}},
	})
	if err != nil {
		t.Fatal(err)
	}
	found := driveResources(result.Catalog)
	want := []string{
		"Material cátedra/Unidad 2|tp.docx",
		"Material cátedra|Clase 1.pdf",
		"Material cátedra|Encuesta",
		"Material cátedra|Notas.xlsx",
		"Material cátedra|programa.pdf",
	}
	if strings.Join(keys(found), "\n") != strings.Join(want, "\n") {
		t.Fatalf("resources:\n%s", strings.Join(keys(found), "\n"))
	}
	pdf := found["Material cátedra|programa.pdf"]
	if pdf.CourseID != 7 || pdf.ModuleName != "Unidad 1" || pdf.Size != 4 || pdf.Modified == 0 ||
		pdf.Drive == nil || pdf.Drive.FileID != "f1" || pdf.Drive.ExportMIME != "" || pdf.URL != "https://drive.google.com/file/d/f1/view" {
		t.Fatalf("pdf = %+v (drive %+v)", pdf, pdf.Drive)
	}
	if slides := found["Material cátedra|Clase 1.pdf"]; slides.Drive.ExportMIME != "application/pdf" || slides.Type != moodle.ResourcePDF {
		t.Fatalf("slides = %+v", slides)
	}
	if sheet := found["Material cátedra|Notas.xlsx"]; sheet.Drive.ExportMIME != xlsxMIME {
		t.Fatalf("sheet = %+v", sheet.Drive)
	}
	if form := found["Material cátedra|Encuesta"]; form.Drive != nil || !form.IsLink() {
		t.Fatalf("form should be a link: %+v", form)
	}
	if result.Catalog.Resources[0].ID != "link-Material cátedra" {
		t.Fatal("the Moodle link itself must stay in the catalog")
	}
	if result.Catalog.Diagnostics.ResourcesBySource["google_drive"] != 5 {
		t.Fatalf("by source = %v", result.Catalog.Diagnostics.ResourcesBySource)
	}
	if len(result.Tree.Roots) != 1 || result.Tree.Roots[0].New || len(result.Tree.Roots[0].Node.Children) != 5 {
		t.Fatalf("tree = %+v", result.Tree.Roots)
	}
}

func TestExpandDuringSyncOnlyPeeksAtNewLinks(t *testing.T) {
	drive := catedraDrive(t)
	client := newTestClient(t, "")
	result, err := Expand(context.Background(), client, catalogWith(driveLink(7, "U1", "Material", catedraURL)), ExpandOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if len(driveResources(result.Catalog)) != 0 || result.Unreviewed != 1 || !result.Tree.Roots[0].New {
		t.Fatalf("unreviewed = %d, resources = %v", result.Unreviewed, keys(driveResources(result.Catalog)))
	}
	if drive.count("list:ROOT") != 0 {
		t.Fatal("sync listed a link the student never reviewed")
	}
	if result.Tree.Roots[0].Node == nil || result.Tree.Roots[0].Node.Name != "Cátedra A" {
		t.Fatalf("root metadata missing: %+v", result.Tree.Roots[0])
	}
}

func TestFullScanListsEverythingButDownloadsNothingNew(t *testing.T) {
	catedraDrive(t)
	client := newTestClient(t, "")
	result, err := Expand(context.Background(), client, catalogWith(driveLink(7, "U1", "Material", catedraURL)), ExpandOptions{Full: true})
	if err != nil {
		t.Fatal(err)
	}
	root := result.Tree.Roots[0]
	if len(root.Node.Children) != 5 || len(driveResources(result.Catalog)) != 0 {
		t.Fatalf("children = %d, resources = %v", len(root.Node.Children), keys(driveResources(result.Catalog)))
	}
	var sub *Node
	for _, child := range root.Node.Children {
		if child.ID == "SUB" {
			sub = child
		}
	}
	if sub == nil || len(sub.Children) != 1 || sub.Children[0].Size != 3 {
		t.Fatalf("subfolder = %+v", sub)
	}
}

func TestExcludedSubfolderIsNotListedAndKeepsItsLastSnapshot(t *testing.T) {
	drive := catedraDrive(t)
	client := newTestClient(t, "")
	catalog := catalogWith(driveLink(7, "U1", "Material", catedraURL))
	scan, err := Expand(context.Background(), client, catalog, ExpandOptions{Full: true})
	if err != nil {
		t.Fatal(err)
	}
	result, err := Expand(context.Background(), client, catalog, ExpandOptions{
		Selection: Selection{Rules: map[string]string{"ROOT": RuleInclude, "SUB": RuleExclude}},
		Previous:  scan.Tree,
	})
	if err != nil {
		t.Fatal(err)
	}
	if drive.count("list:SUB") != 1 {
		t.Fatalf("excluded folder listed again during sync (%d lists)", drive.count("list:SUB"))
	}
	if _, ok := driveResources(result.Catalog)["Material/Unidad 2|tp.docx"]; ok {
		t.Fatal("excluded file downloaded")
	}
	for _, child := range result.Tree.Roots[0].Node.Children {
		if child.ID == "SUB" && len(child.Children) != 1 {
			t.Fatalf("snapshot of the excluded folder lost: %+v", child)
		}
	}
}

func TestIncludedFileInsideExcludedFolderIsStillReached(t *testing.T) {
	catedraDrive(t)
	client := newTestClient(t, "")
	catalog := catalogWith(driveLink(7, "U1", "Material", catedraURL))
	scan, _ := Expand(context.Background(), client, catalog, ExpandOptions{Full: true})
	result, err := Expand(context.Background(), client, catalog, ExpandOptions{
		Selection: Selection{Rules: map[string]string{"ROOT": RuleExclude, "f5": RuleInclude}},
		Previous:  scan.Tree,
	})
	if err != nil {
		t.Fatal(err)
	}
	found := driveResources(result.Catalog)
	if len(found) != 1 || found["Material/Unidad 2|tp.docx"].Drive == nil {
		t.Fatalf("resources = %v", keys(found))
	}
}

func TestNewFileInIncludedFolderIsDownloaded(t *testing.T) {
	drive := catedraDrive(t)
	client := newTestClient(t, "")
	catalog := catalogWith(driveLink(7, "U1", "Material", catedraURL))
	options := ExpandOptions{Selection: Selection{Rules: map[string]string{"ROOT": RuleInclude}}}
	first, _ := Expand(context.Background(), client, catalog, options)
	drive.mu.Lock()
	drive.files["f9"] = &fakeFile{ID: "f9", Name: "nuevo.pdf", MimeType: "application/pdf", Parent: "ROOT", Content: "x", Public: true}
	drive.mu.Unlock()
	options.Previous = first.Tree
	second, err := Expand(context.Background(), client, catalog, options)
	if err != nil {
		t.Fatal(err)
	}
	if _, ok := driveResources(second.Catalog)["Material|nuevo.pdf"]; !ok {
		t.Fatalf("resources = %v", keys(driveResources(second.Catalog)))
	}
}

func TestPrivateLinkFailsOnlyOnceReviewed(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "PRIV", Name: "Privada", MimeType: folderMIME})
	client := newTestClient(t, "")
	catalog := catalogWith(driveLink(7, "U1", "Privada", "https://drive.google.com/drive/folders/PRIV"))
	unreviewed, err := Expand(context.Background(), client, catalog, ExpandOptions{})
	if err != nil {
		t.Fatal(err)
	}
	if len(unreviewed.Failures) != 0 || !strings.Contains(unreviewed.Tree.Roots[0].Error, "privada") {
		t.Fatalf("failures = %+v, root = %+v", unreviewed.Failures, unreviewed.Tree.Roots[0])
	}
	reviewed, _ := Expand(context.Background(), client, catalog, ExpandOptions{
		Selection: Selection{Rules: map[string]string{"PRIV": RuleInclude}},
	})
	if len(reviewed.Failures) != 1 || reviewed.Failures[0].Resource != "Privada" || !strings.Contains(reviewed.Failures[0].Error, "conectá Google") {
		t.Fatalf("failures = %+v", reviewed.Failures)
	}
}

func TestShortcutCyclesDoNotLoopForever(t *testing.T) {
	newFakeDrive(t,
		&fakeFile{ID: "A", Name: "A", MimeType: folderMIME, Public: true},
		&fakeFile{ID: "toA", Name: "volver", MimeType: shortcutMIME, Parent: "A", ShortcutTarget: "A", Public: true},
		&fakeFile{ID: "toF", Name: "atajo.pdf", MimeType: shortcutMIME, Parent: "A", ShortcutTarget: "real", Public: true},
		&fakeFile{ID: "real", Name: "real.pdf", MimeType: "application/pdf", Content: "pdf", Public: true},
	)
	client := newTestClient(t, "")
	result, err := Expand(context.Background(), client, catalogWith(driveLink(7, "U1", "A", "https://drive.google.com/drive/folders/A")), ExpandOptions{
		Selection: Selection{Rules: map[string]string{"A": RuleInclude}},
	})
	if err != nil {
		t.Fatal(err)
	}
	found := driveResources(result.Catalog)
	if len(found) != 1 || found["A|real.pdf"].Drive.FileID != "real" {
		t.Fatalf("resources = %v", keys(found))
	}
}

func TestSameFileLinkedTwiceInACourseDownloadsOnce(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "F", Name: "guia.pdf", MimeType: "application/pdf", Content: "1", Public: true})
	client := newTestClient(t, "")
	url := "https://drive.google.com/file/d/F/view"
	result, err := Expand(context.Background(), client, catalogWith(driveLink(7, "U1", "Guía", url), driveLink(7, "U2", "Guía otra vez", url)), ExpandOptions{
		Selection: Selection{Rules: map[string]string{"F": RuleInclude}},
	})
	if err != nil {
		t.Fatal(err)
	}
	found := driveResources(result.Catalog)
	if len(found) != 1 || found["|guia.pdf"].ModuleName != "U1" {
		t.Fatalf("resources = %v", keys(found))
	}
}

func TestExpandWithoutCredentialsOnlyWarns(t *testing.T) {
	client := NewClient(Credentials{}, NewTokenSource(Credentials{}, ""))
	catalog := catalogWith(driveLink(7, "U1", "Material", catedraURL))
	result, err := Expand(context.Background(), client, catalog, ExpandOptions{Previous: Tree{Roots: []*Root{{ID: "ROOT", CourseID: 7}}}})
	if err != nil || len(result.Catalog.Resources) != 1 || len(result.Catalog.Diagnostics.Warnings) != 1 {
		t.Fatalf("result = %+v, err = %v", result.Catalog, err)
	}
	if len(result.Tree.Roots) != 0 {
		t.Fatalf("a build without Drive must not report roots: %+v", result.Tree.Roots)
	}
}

func TestFullScanListsFoldersInParallelAndReportsProgress(t *testing.T) {
	files := []*fakeFile{{ID: "ROOT", Name: "Universidad", MimeType: folderMIME, Public: true}}
	for i := 0; i < 12; i++ {
		folder := fmt.Sprintf("C%02d", i)
		files = append(files,
			&fakeFile{ID: folder, Name: "Cátedra " + folder, MimeType: folderMIME, Parent: "ROOT", Public: true},
			&fakeFile{ID: folder + "-f", Name: "apunte.pdf", MimeType: "application/pdf", Parent: folder, Content: "x", Public: true},
		)
	}
	drive := newFakeDrive(t, files...)
	drive.listDelay = 30 * time.Millisecond
	client := newTestClient(t, "")
	var messages []string
	var mu sync.Mutex
	progress := func(message string) {
		mu.Lock()
		defer mu.Unlock()
		messages = append(messages, message)
	}
	original := progressEvery
	progressEvery = 0
	t.Cleanup(func() { progressEvery = original })
	result, err := Expand(context.Background(), client, catalogWith(driveLink(7, "U1", "Material", "https://drive.google.com/drive/folders/ROOT")),
		ExpandOptions{Full: true, Progress: progress})
	if err != nil {
		t.Fatal(err)
	}
	if drive.maxInFlight.Load() < 2 {
		t.Fatalf("folders were listed one at a time (max in flight %d)", drive.maxInFlight.Load())
	}
	children := result.Tree.Roots[0].Node.Children
	if len(children) != 12 || children[0].ID != "C00" || children[11].ID != "C11" || len(children[5].Children) != 1 {
		t.Fatalf("tree order or content changed: %d children", len(children))
	}
	last := messages[len(messages)-1]
	if !strings.Contains(last, "13 carpetas") || !strings.Contains(last, "12 archivos") {
		t.Fatalf("progress = %q", messages)
	}
}
