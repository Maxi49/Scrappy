package syncer

import (
	"context"
	"errors"
	"io"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"testing"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

type fakeFetcher struct {
	mu       sync.Mutex
	content  map[string]string
	failures map[string]int // fails this many times before succeeding
	opened   []string
}

func (f *fakeFetcher) Open(_ context.Context, resource moodle.Resource) (io.ReadCloser, int64, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.opened = append(f.opened, resource.Drive.FileID)
	if f.failures[resource.Drive.FileID] > 0 {
		f.failures[resource.Drive.FileID]--
		return nil, 0, errors.New("Google Drive respondió HTTP 500")
	}
	content := f.content[resource.Drive.FileID]
	return io.NopCloser(strings.NewReader(content)), int64(len(content)), nil
}

func driveResource(fileID string, modified int64) moodle.Resource {
	return moodle.Resource{
		ID: "drive-" + fileID, CourseID: 7, CourseName: "Materia", ModuleName: "Unidad",
		Name: "apunte.pdf", Subfolder: "Cátedra", URL: "https://drive.google.com/file/d/" + fileID + "/view",
		Type: moodle.ResourcePDF, MIME: "application/pdf", Modified: modified, Source: "google_drive",
		Accessible: true, Drive: &moodle.DriveRef{FileID: fileID, ExportMIME: "application/pdf"},
	}
}

func TestDriveResourcesDownloadThroughTheFetcher(t *testing.T) {
	client, _ := moodle.NewClient("https://moodle.invalid", "token")
	fetcher := &fakeFetcher{content: map[string]string{"F1": "%PDF-1"}, failures: map[string]int{"F1": 1}}
	directory := t.TempDir()
	options := Options{OutputPath: directory, Workers: 1, Fetcher: fetcher}
	catalog := moodle.Catalog{Resources: []moodle.Resource{driveResource("F1", 100)}}

	first, err := Run(context.Background(), client, catalog, options)
	if err != nil || first.Downloaded != 1 {
		t.Fatalf("report=%#v err=%v", first, err)
	}
	content, err := os.ReadFile(filepath.Join(directory, "Materia", "Unidad", "Cátedra", "apunte.pdf"))
	if err != nil || string(content) != "%PDF-1" {
		t.Fatalf("content=%q err=%v", content, err)
	}

	second, err := Run(context.Background(), client, catalog, options)
	if err != nil || second.Unchanged != 1 || len(fetcher.opened) != 2 {
		t.Fatalf("unchanged run: report=%#v opened=%v err=%v", second, fetcher.opened, err)
	}

	fetcher.content["F1"] = "%PDF-2"
	edited := moodle.Catalog{Resources: []moodle.Resource{driveResource("F1", 200)}}
	third, err := Run(context.Background(), client, edited, options)
	if err != nil || third.Downloaded != 1 {
		t.Fatalf("edited run: report=%#v err=%v", third, err)
	}
	content, _ = os.ReadFile(filepath.Join(directory, "Materia", "Unidad", "Cátedra", "apunte.pdf"))
	if string(content) != "%PDF-2" {
		t.Fatalf("edited content = %q", content)
	}
}

func TestDriveResourceWithoutFetcherFails(t *testing.T) {
	client, _ := moodle.NewClient("https://moodle.invalid", "token")
	catalog := moodle.Catalog{Resources: []moodle.Resource{driveResource("F1", 100)}}
	report, err := Run(context.Background(), client, catalog, Options{OutputPath: t.TempDir(), Workers: 1})
	if err == nil || report.Failed != 1 {
		t.Fatalf("report=%#v err=%v", report, err)
	}
}

func TestExtraFailuresAndDriveFieldsReachTheReport(t *testing.T) {
	client, _ := moodle.NewClient("https://moodle.invalid", "token")
	report, err := Run(context.Background(), client, moodle.Catalog{}, Options{
		OutputPath: t.TempDir(), Workers: 1,
		ExtraFailures:   []Failure{{Course: "Materia", Module: "U1", Resource: "Cátedra", Error: "Google Drive: privada"}},
		DriveUnreviewed: 2,
		AuthExpired:     func() bool { return true },
	})
	if err == nil || report.Failed != 1 || report.DriveUnreviewed != 2 || !report.GoogleAuthExpired {
		t.Fatalf("report=%#v err=%v", report, err)
	}
}
