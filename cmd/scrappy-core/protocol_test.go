package main

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const (
	testPassword = " clave secreta "
	testToken    = "tok-123"
)

func fakeMoodle(t *testing.T) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(response http.ResponseWriter, request *http.Request) {
		reply := func(value any) { _ = json.NewEncoder(response).Encode(value) }
		switch {
		case request.URL.Path == "/login/token.php":
			_ = request.ParseForm()
			if request.PostForm.Get("username") == "alumno" && request.PostForm.Get("password") == testPassword {
				reply(map[string]any{"token": testToken})
			} else {
				reply(map[string]any{"error": "Datos de acceso inválidos"})
			}
		case request.URL.Path == "/webservice/rest/server.php":
			_ = request.ParseForm()
			if request.PostForm.Get("wstoken") != testToken {
				reply(map[string]any{"exception": "moodle_exception", "errorcode": "invalidtoken", "message": "Token inválido"})
				return
			}
			switch request.PostForm.Get("wsfunction") {
			case "core_webservice_get_site_info":
				reply(map[string]any{"userid": 5, "functions": []any{}})
			case "core_enrol_get_users_courses":
				reply([]map[string]any{{"id": 1, "fullname": "Algebra"}, {"id": 2, "fullname": "Rota"}})
			case "core_course_get_contents":
				if request.PostForm.Get("courseid") != "1" {
					reply(map[string]any{"exception": "required_capability_exception", "message": "Sin acceso"})
					return
				}
				reply([]map[string]any{{"id": 1, "name": "Unidad 1", "section": 1, "modules": []map[string]any{{
					"id": 10, "name": "Guía", "modname": "resource", "uservisible": 1,
					"contents": []map[string]any{{
						"type": "file", "filename": "guia.pdf", "filepath": "/", "filesize": 4,
						"fileurl": "http://" + request.Host + "/webservice/pluginfile.php/7/mod_resource/content/1/guia.pdf",
					}},
				}}}})
			default:
				reply(map[string]any{"exception": "webservice_access_exception", "message": "no disponible"})
			}
		case strings.HasPrefix(request.URL.Path, "/webservice/pluginfile.php/"):
			if request.URL.Query().Get("token") != testToken {
				http.Redirect(response, request, "/login/index.php", http.StatusFound)
				return
			}
			_, _ = response.Write([]byte("%PDF"))
		default:
			http.NotFound(response, request)
		}
	}))
	t.Cleanup(server.Close)
	return server
}

type protocolRun struct {
	code   int
	raw    string
	events []map[string]any
}

func (r protocolRun) result(t *testing.T) map[string]any {
	t.Helper()
	var results []map[string]any
	for _, event := range r.events {
		if event["event"] == "result" {
			results = append(results, event)
		}
	}
	if len(results) != 1 {
		t.Fatalf("expected exactly one result event, got %d:\n%s", len(results), r.raw)
	}
	if r.events[len(r.events)-1]["event"] != "result" {
		t.Fatalf("result must be the last event:\n%s", r.raw)
	}
	return results[0]
}

func serveRequest(t *testing.T, ctx context.Context, input string) protocolRun {
	t.Helper()
	var stdout bytes.Buffer
	code := serve(ctx, strings.NewReader(input), &stdout)
	run := protocolRun{code: code, raw: stdout.String()}
	for _, line := range strings.Split(strings.TrimSpace(run.raw), "\n") {
		var event map[string]any
		if err := json.Unmarshal([]byte(line), &event); err != nil {
			t.Fatalf("stdout line is not JSON: %q", line)
		}
		run.events = append(run.events, event)
	}
	return run
}

func requestJSON(t *testing.T, fields map[string]any) string {
	t.Helper()
	encoded, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	return string(encoded) + "\n"
}

func syncRequest(t *testing.T, base, output string, courseIDs ...int) string {
	courses := make([]map[string]any, 0, len(courseIDs))
	for _, id := range courseIDs {
		courses = append(courses, map[string]any{"id": id, "name": "Materia", "mode": "update", "scan_existing": true})
	}
	return requestJSON(t, map[string]any{
		"action": "sync", "base_url": base, "username": "alumno", "password": testPassword,
		"output_path": output, "courses": courses,
	})
}

func TestCoursesActionReturnsTokenAndCourses(t *testing.T) {
	server := fakeMoodle(t)
	run := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "courses", "base_url": server.URL, "username": "alumno", "password": testPassword,
	}))
	result := run.result(t)
	if run.code != 0 || result["ok"] != true || result["token"] != testToken {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
	if courses, _ := result["courses"].([]any); len(courses) != 2 {
		t.Fatalf("expected 2 courses, got %v", result["courses"])
	}
	if strings.Contains(run.raw, testPassword) {
		t.Fatal("password leaked to stdout")
	}
}

func TestSyncActionStreamsProgressAndDownloads(t *testing.T) {
	server := fakeMoodle(t)
	output := t.TempDir()
	run := serveRequest(t, context.Background(), syncRequest(t, server.URL, output, 1))
	result := run.result(t)
	if run.code != 0 || result["ok"] != true {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
	if run.events[0]["event"] != "progress" {
		t.Fatalf("expected progress before the result:\n%s", run.raw)
	}
	report, _ := result["report"].(map[string]any)
	if report["downloaded"] != float64(1) {
		t.Fatalf("expected 1 download, report %v", report)
	}
	if _, err := os.Stat(filepath.Join(output, "Materia", "Unidad 1", "guia.pdf")); err != nil {
		t.Fatalf("downloaded file missing: %v", err)
	}
	for _, secret := range []string{testPassword, testToken} {
		if strings.Contains(run.raw, secret) {
			t.Fatalf("secret %q leaked to stdout", secret)
		}
	}
}

func TestPartialSyncSendsOneFailedResultWithItsReport(t *testing.T) {
	server := fakeMoodle(t)
	run := serveRequest(t, context.Background(), syncRequest(t, server.URL, t.TempDir(), 1, 2))
	result := run.result(t)
	report, _ := result["report"].(map[string]any)
	if run.code != 1 || result["ok"] != false || report == nil {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
	if report["downloaded"] != float64(1) || report["failed"] != float64(1) {
		t.Fatalf("expected the healthy course to download and one failure, report %v", report)
	}
}

func TestRejectedCredentialsReturnTheMoodleError(t *testing.T) {
	server := fakeMoodle(t)
	run := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "courses", "base_url": server.URL, "username": "alumno", "password": "otra",
	}))
	result := run.result(t)
	if run.code != 1 || result["ok"] != false || !strings.Contains(result["error"].(string), "Datos de acceso inválidos") {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
}

func TestInvalidRequestJSONExitsWithCode2(t *testing.T) {
	run := serveRequest(t, context.Background(), "esto no es json\n")
	if result := run.result(t); run.code != 2 || result["ok"] != false {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
}

func TestUnknownActionIsAnError(t *testing.T) {
	run := serveRequest(t, context.Background(), requestJSON(t, map[string]any{"action": "borrar_todo"}))
	if result := run.result(t); run.code != 1 || result["ok"] != false {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
}

func TestCancelledRequestReportsCancellation(t *testing.T) {
	server := fakeMoodle(t)
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	run := serveRequest(t, ctx, syncRequest(t, server.URL, t.TempDir(), 1))
	if result := run.result(t); run.code != 1 || result["cancelled"] != true {
		t.Fatalf("unexpected result (code %d): %v", run.code, result)
	}
}

func TestStdinEOFOnlyCancelsWhenRequested(t *testing.T) {
	server := fakeMoodle(t)
	plain := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "courses", "base_url": server.URL, "username": "alumno", "password": testPassword,
	}))
	if plain.result(t)["ok"] != true {
		t.Fatalf("a piped request without the flag must not be cancelled:\n%s", plain.raw)
	}
	opted := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "sync", "base_url": server.URL, "username": "alumno", "password": testPassword,
		"output_path": t.TempDir(), "cancel_on_stdin_close": true,
		"courses": []map[string]any{{"id": 1, "name": "Materia", "mode": "update", "scan_existing": true}},
	}))
	if result := opted.result(t); result["ok"] == true || result["cancelled"] != true {
		// EOF arrives right after the request, so the sync must not complete normally.
		t.Fatalf("closing stdin did not cancel an opted-in request:\n%s", opted.raw)
	}
}

func TestDuplicateActionsFindAndRemoveIdenticalCopies(t *testing.T) {
	output := t.TempDir()
	folder := filepath.Join(output, "Materia", "Unidad")
	if err := os.MkdirAll(folder, 0o755); err != nil {
		t.Fatal(err)
	}
	for name, content := range map[string]string{"apunte.pdf": "igual", "apunte_1.pdf": "igual", "apunte_2.pdf": "distinto"} {
		if err := os.WriteFile(filepath.Join(folder, name), []byte(content), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	found := serveRequest(t, context.Background(), requestJSON(t, map[string]any{"action": "duplicates", "output_path": output}))
	result := found.result(t)
	duplicates, _ := result["duplicates"].([]any)
	if found.code != 0 || len(duplicates) != 1 || result["bytes"] != float64(5) {
		t.Fatalf("unexpected scan (code %d): %v", found.code, result)
	}
	path := duplicates[0].(map[string]any)["path"]

	removed := serveRequest(t, context.Background(), requestJSON(t, map[string]any{
		"action": "remove_duplicates", "output_path": output, "paths": []any{path},
	}))
	if result := removed.result(t); removed.code != 0 || len(result["removed"].([]any)) != 1 {
		t.Fatalf("unexpected removal (code %d): %v", removed.code, result)
	}
	if _, err := os.Stat(filepath.Join(folder, "apunte_1.pdf")); !os.IsNotExist(err) {
		t.Fatal("identical copy was not removed")
	}
	if _, err := os.Stat(filepath.Join(folder, "apunte_2.pdf")); err != nil {
		t.Fatal("a copy with different content was removed")
	}
}

// lineWatcher passes each stdout line to onLine as it is written, so a test
// can react to events (like a browser would) while serve is still running.
type lineWatcher struct {
	buffer bytes.Buffer
	onLine func(map[string]any)
	seen   int
}

func (w *lineWatcher) Write(p []byte) (int, error) {
	n, err := w.buffer.Write(p)
	lines := strings.Split(w.buffer.String(), "\n")
	for ; w.seen < len(lines)-1; w.seen++ {
		var event map[string]any
		if json.Unmarshal([]byte(lines[w.seen]), &event) == nil {
			w.onLine(event)
		}
	}
	return n, err
}

func TestGoogleLoginShowsConsentURLAndStopsWhenCancelled(t *testing.T) {
	t.Setenv("SCRAPPY_GOOGLE_CLIENT_ID", "CID")
	t.Setenv("SCRAPPY_GOOGLE_CLIENT_SECRET", "CSECRET")
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	var consent string
	watcher := &lineWatcher{onLine: func(event map[string]any) {
		if event["event"] == "open_url" {
			consent, _ = event["url"].(string)
			cancel()
		}
	}}
	code := serve(ctx, strings.NewReader(requestJSON(t, map[string]any{"action": "google_login"})), watcher)
	if code != 1 || !strings.Contains(consent, "client_id=CID") || !strings.Contains(consent, "code_challenge=") {
		t.Fatalf("code = %d, consent = %q\n%s", code, consent, watcher.buffer.String())
	}
	if !strings.Contains(watcher.buffer.String(), `"cancelled":true`) {
		t.Fatalf("expected a cancelled result:\n%s", watcher.buffer.String())
	}
}

func TestGoogleLoginWithoutAppCredentialsFails(t *testing.T) {
	t.Setenv("SCRAPPY_GOOGLE_CLIENT_ID", "")
	t.Setenv("SCRAPPY_GOOGLE_CLIENT_SECRET", "")
	run := serveRequest(t, context.Background(), requestJSON(t, map[string]any{"action": "google_login"}))
	result := run.result(t)
	if run.code != 1 || result["ok"] != false || !strings.Contains(result["error"].(string), "Google") {
		t.Fatalf("result = %v", result)
	}
}
