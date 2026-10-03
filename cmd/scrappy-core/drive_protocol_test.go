package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/Maxi49/Scrappy/internal/gdrive"
)

// fakeMoodleWithDrive serves one course whose only content is a URL activity
// pointing at a Drive folder.
func fakeMoodleWithDrive(t *testing.T) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		reply := func(value any) { _ = json.NewEncoder(response).Encode(value) }
		_ = request.ParseForm()
		switch request.PostForm.Get("wsfunction") {
		case "core_webservice_get_site_info":
			reply(map[string]any{"userid": 5, "functions": []any{}})
		case "core_course_get_contents":
			reply([]map[string]any{{"id": 1, "name": "Unidad 1", "section": 1, "modules": []map[string]any{{
				"id": 20, "name": "Material de la cátedra", "modname": "url", "uservisible": 1,
				"contents": []map[string]any{{"type": "url", "filename": "Material", "fileurl": "https://drive.google.com/drive/folders/ROOT?usp=sharing"}},
			}}}})
		default:
			reply(map[string]any{"exception": "webservice_access_exception", "message": "no disponible"})
		}
	}))
	t.Cleanup(server.Close)
	return server
}

// fakeDriveAPI serves a public folder ROOT holding apunte.pdf.
func fakeDriveAPI(t *testing.T) {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		if request.URL.Query().Get("key") != "KEY" {
			http.Error(response, `{"error":{"errors":[{"reason":"notFound"}]}}`, http.StatusNotFound)
			return
		}
		reply := func(value any) { _ = json.NewEncoder(response).Encode(value) }
		switch {
		case request.URL.Path == "/files/ROOT":
			reply(map[string]any{"id": "ROOT", "name": "Cátedra", "mimeType": "application/vnd.google-apps.folder"})
		case request.URL.Path == "/files" && strings.Contains(request.URL.Query().Get("q"), "'ROOT' in parents"):
			reply(map[string]any{"files": []map[string]any{{
				"id": "F1", "name": "apunte.pdf", "mimeType": "application/pdf", "size": "4", "modifiedTime": "2026-09-01T10:00:00Z",
			}}})
		case request.URL.Path == "/files/F1" && request.URL.Query().Get("alt") == "media":
			_, _ = response.Write([]byte("%PDF"))
		default:
			http.NotFound(response, request)
		}
	}))
	t.Cleanup(server.Close)
	t.Cleanup(gdrive.UseEndpoints(server.URL, server.URL+"/token"))
	t.Setenv("SCRAPPY_GOOGLE_API_KEY", "KEY")
	t.Setenv("SCRAPPY_GOOGLE_CLIENT_ID", "")
	t.Setenv("SCRAPPY_GOOGLE_CLIENT_SECRET", "")
}

func driveRequest(t *testing.T, action, base, output string) string {
	return requestJSON(t, map[string]any{
		"action": action, "base_url": base, "token": testToken, "output_path": output,
		"courses": []map[string]any{{"id": 1, "name": "Sistemas", "mode": "update", "scan_existing": true}},
	})
}

func TestDriveScanReturnsTheTreeWithoutDownloading(t *testing.T) {
	fakeDriveAPI(t)
	moodleServer := fakeMoodleWithDrive(t)
	output := t.TempDir()
	run := serveRequest(t, context.Background(), driveRequest(t, "drive_scan", moodleServer.URL, output))
	result := run.result(t)
	if run.code != 0 || result["ok"] != true {
		t.Fatalf("result = %v\n%s", result, run.raw)
	}
	tree := result["tree"].(map[string]any)
	root := tree["roots"].([]any)[0].(map[string]any)
	if root["new"] != true || root["link_name"] != "Material de la cátedra" || root["node"].(map[string]any)["children"] == nil {
		t.Fatalf("root = %v", root)
	}
	if _, err := os.Stat(filepath.Join(output, ".scrappy", "drive-tree.json")); err != nil {
		t.Fatal("drive-tree.json not written")
	}
	if _, err := os.Stat(filepath.Join(output, "Sistemas")); err == nil {
		t.Fatal("drive_scan downloaded files")
	}
}

func TestDriveSelectionSaveValidatesAndStoresRules(t *testing.T) {
	output := t.TempDir()
	run := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "drive_selection_save", "output_path": output, "rules": map[string]string{"ROOT": "include"},
	}))
	if result := run.result(t); result["ok"] != true {
		t.Fatalf("result = %v", result)
	}
	selection, err := gdrive.LoadSelection(output)
	if err != nil || selection.Rules["ROOT"] != "include" {
		t.Fatalf("selection = %+v, err = %v", selection, err)
	}
	bad := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "drive_selection_save", "output_path": output, "rules": map[string]string{"ROOT": "maybe"},
	}))
	if result := bad.result(t); result["ok"] != false {
		t.Fatalf("invalid rule accepted: %v", result)
	}
}

func TestSyncDownloadsOnlyReviewedDriveLinks(t *testing.T) {
	fakeDriveAPI(t)
	moodleServer := fakeMoodleWithDrive(t)
	output := t.TempDir()
	target := filepath.Join(output, "Sistemas", "Unidad 1", "Material de la cátedra", "apunte.pdf")

	unreviewed := serveRequest(t, context.Background(), driveRequest(t, "sync", moodleServer.URL, output))
	report := unreviewed.result(t)["report"].(map[string]any)
	if report["drive_unreviewed"] != float64(1) {
		t.Fatalf("report = %v", report)
	}
	if _, err := os.Stat(target); err == nil {
		t.Fatal("an unreviewed Drive link was downloaded")
	}

	if err := gdrive.SaveSelection(output, gdrive.Selection{Rules: map[string]string{"ROOT": "include"}}); err != nil {
		t.Fatal(err)
	}
	reviewed := serveRequest(t, context.Background(), driveRequest(t, "sync", moodleServer.URL, output))
	if result := reviewed.result(t); result["ok"] != true {
		t.Fatalf("result = %v\n%s", result, reviewed.raw)
	}
	content, err := os.ReadFile(target)
	if err != nil || string(content) != "%PDF" {
		t.Fatalf("content = %q, err = %v", content, err)
	}
}
