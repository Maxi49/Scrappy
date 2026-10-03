package gdrive

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"testing"
)

type fakeFile struct {
	ID, Name, MimeType, Parent, Modified string
	Content                              string
	Public                               bool   // readable with the API key
	ResourceKey                          string // required with the API key when set
	Trashed                              bool
	ShortcutTarget                       string
	ExportTooLarge                       bool
	RateLimitOnce                        bool
}

// fakeDrive answers the subset of Drive v3 that Scrappy uses. The API key
// "KEY" only reads public files; the bearer "AT2" (see fakeTokenServer) reads
// everything.
type fakeDrive struct {
	t      *testing.T
	server *httptest.Server
	mu     sync.Mutex
	files  map[string]*fakeFile
	hits   map[string]int
}

var listQuery = regexp.MustCompile(`^'([\w-]+)' in parents and trashed = false$`)

func newFakeDrive(t *testing.T, files ...*fakeFile) *fakeDrive {
	t.Helper()
	drive := &fakeDrive{t: t, files: map[string]*fakeFile{}, hits: map[string]int{}}
	for _, file := range files {
		drive.files[file.ID] = file
	}
	drive.server = httptest.NewServer(http.HandlerFunc(drive.serve))
	original := apiBase
	apiBase = drive.server.URL + "/drive/v3"
	t.Cleanup(func() {
		drive.server.Close()
		apiBase = original
	})
	return drive
}

func (d *fakeDrive) count(key string) int {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.hits[key]
}

func googleError(w http.ResponseWriter, status int, reason string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(map[string]any{"error": map[string]any{
		"code": status, "message": reason, "errors": []map[string]string{{"reason": reason}},
	}})
}

func (d *fakeDrive) readable(r *http.Request, file *fakeFile) bool {
	if r.Header.Get("Authorization") == "Bearer AT2" {
		return true
	}
	if r.URL.Query().Get("key") != "KEY" || !file.Public {
		return false
	}
	if file.ResourceKey == "" {
		return true
	}
	return strings.Contains(r.Header.Get("X-Goog-Drive-Resource-Keys"), file.ID+"/"+file.ResourceKey)
}

func (d *fakeDrive) metadata(file *fakeFile) map[string]any {
	meta := map[string]any{
		"id": file.ID, "name": file.Name, "mimeType": file.MimeType,
		"modifiedTime": file.Modified, "trashed": file.Trashed,
	}
	if file.Modified == "" {
		meta["modifiedTime"] = "2026-09-01T10:00:00.000Z"
	}
	if !strings.HasPrefix(file.MimeType, "application/vnd.google-apps.") {
		meta["size"] = strconv.Itoa(len(file.Content))
	}
	if file.ResourceKey != "" {
		meta["resourceKey"] = file.ResourceKey
	}
	if file.ShortcutTarget != "" {
		target := d.files[file.ShortcutTarget]
		meta["shortcutDetails"] = map[string]string{"targetId": target.ID, "targetMimeType": target.MimeType}
	}
	if strings.HasPrefix(file.MimeType, "application/vnd.google-apps.") {
		meta["exportLinks"] = map[string]string{
			"application/pdf": d.server.URL + "/export-link/" + file.ID + "?format=pdf",
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": d.server.URL + "/export-link/" + file.ID + "?format=xlsx",
		}
	}
	return meta
}

func (d *fakeDrive) serve(w http.ResponseWriter, r *http.Request) {
	d.mu.Lock()
	defer d.mu.Unlock()
	query := r.URL.Query()
	path := r.URL.Path
	if strings.HasPrefix(path, "/export-link/") {
		id := strings.TrimPrefix(path, "/export-link/")
		d.hits["export-link:"+id]++
		w.Write([]byte("LINK:" + query.Get("format") + ":" + d.files[id].Content))
		return
	}
	if !strings.HasPrefix(path, "/drive/v3/files") {
		http.NotFound(w, r)
		return
	}
	if query.Get("supportsAllDrives") != "true" {
		d.t.Errorf("request without supportsAllDrives: %s", r.URL)
	}
	if path == "/drive/v3/files" {
		d.list(w, r)
		return
	}
	rest := strings.TrimPrefix(path, "/drive/v3/files/")
	id, export := strings.CutSuffix(rest, "/export")
	file := d.files[id]
	if file == nil || !d.readable(r, file) {
		d.hits["denied:"+id]++
		googleError(w, http.StatusNotFound, "notFound")
		return
	}
	switch {
	case export:
		d.hits["export:"+id]++
		if file.ExportTooLarge {
			googleError(w, http.StatusForbidden, "exportSizeLimitExceeded")
			return
		}
		w.Write([]byte("EXPORT:" + query.Get("mimeType") + ":" + file.Content))
	case query.Get("alt") == "media":
		d.hits["media:"+id]++
		if file.RateLimitOnce {
			file.RateLimitOnce = false
			googleError(w, http.StatusForbidden, "userRateLimitExceeded")
			return
		}
		w.Write([]byte(file.Content))
	default:
		d.hits["get:"+id]++
		json.NewEncoder(w).Encode(d.metadata(file))
	}
}

func (d *fakeDrive) list(w http.ResponseWriter, r *http.Request) {
	query := r.URL.Query()
	if query.Get("includeItemsFromAllDrives") != "true" {
		d.t.Errorf("list without includeItemsFromAllDrives: %s", r.URL)
	}
	match := listQuery.FindStringSubmatch(query.Get("q"))
	if match == nil {
		d.t.Errorf("unexpected list query %q", query.Get("q"))
		googleError(w, http.StatusBadRequest, "invalid")
		return
	}
	parent := d.files[match[1]]
	if parent == nil || !d.readable(r, parent) {
		googleError(w, http.StatusNotFound, "notFound")
		return
	}
	d.hits["list:"+parent.ID]++
	var children []*fakeFile
	for _, file := range d.files {
		if file.Parent == parent.ID && !file.Trashed {
			children = append(children, file)
		}
	}
	sort.Slice(children, func(i, j int) bool { return children[i].ID < children[j].ID })
	// Two per page so every multi-file test exercises pagination.
	start, _ := strconv.Atoi(query.Get("pageToken"))
	end := min(start+2, len(children))
	page := map[string]any{"files": []map[string]any{}}
	items := []map[string]any{}
	for _, child := range children[start:end] {
		items = append(items, d.metadata(child))
	}
	page["files"] = items
	if end < len(children) {
		page["nextPageToken"] = strconv.Itoa(end)
	}
	json.NewEncoder(w).Encode(page)
}
