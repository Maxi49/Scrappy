package gdrive

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

const (
	folderMIME = "application/vnd.google-apps.folder"
	docMIME    = "application/vnd.google-apps.document"
	sheetMIME  = "application/vnd.google-apps.spreadsheet"
	xlsxMIME   = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

func newTestClient(t *testing.T, refresh string) *Client {
	t.Helper()
	fakeTokenServer(t, nil)
	return NewClient(testCreds, NewTokenSource(testCreds, refresh))
}

func TestGetPublicFileUsesTheAPIKeyOnly(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "P", Name: "guia.pdf", MimeType: "application/pdf", Content: "%PDF", Public: true})
	client := newTestClient(t, "RT1")
	file, oauth, err := client.Get(context.Background(), "P", "")
	if err != nil || oauth || file.Name != "guia.pdf" || file.Size != 4 {
		t.Fatalf("file = %+v, oauth = %v, err = %v", file, oauth, err)
	}
}

func TestGetPrivateFileFallsBackToOAuth(t *testing.T) {
	drive := newFakeDrive(t, &fakeFile{ID: "X", Name: "privado", MimeType: folderMIME})
	client := newTestClient(t, "RT1")
	file, oauth, err := client.Get(context.Background(), "X", "")
	if err != nil || !oauth || file.MimeType != folderMIME {
		t.Fatalf("file = %+v, oauth = %v, err = %v", file, oauth, err)
	}
	if drive.count("denied:X") != 1 {
		t.Fatalf("expected one API-key attempt, got %d", drive.count("denied:X"))
	}
}

func TestGetPrivateFileWithoutSessionAsksToConnectGoogle(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "X", Name: "privado", MimeType: folderMIME})
	client := newTestClient(t, "")
	_, _, err := client.Get(context.Background(), "X", "")
	if !errors.Is(err, ErrPrivate) {
		t.Fatalf("err = %v", err)
	}
}

func TestGetUnreachableFileWithSessionReportsNoAccess(t *testing.T) {
	newFakeDrive(t)
	client := newTestClient(t, "RT1")
	_, _, err := client.Get(context.Background(), "MISSING", "")
	if !errors.Is(err, ErrNoAccess) {
		t.Fatalf("err = %v", err)
	}
}

func TestGetPreservesGoogleDenialReason(t *testing.T) {
	for _, test := range []struct {
		reason   string
		status   int
		noAccess bool
	}{
		{"insufficientPermissions", 403, false},
		{"accessNotConfigured", 403, false},
		{"domainPolicy", 403, false},
		{"userRateLimitExceeded", 403, false},
		{"insufficientFilePermissions", 403, true},
		{"notFound", 404, true},
	} {
		t.Run(test.reason, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				googleError(w, test.status, test.reason)
			}))
			defer server.Close()
			original := apiBase
			apiBase = server.URL
			defer func() { apiBase = original }()
			client := newTestClient(t, "RT1")
			client.retryWait = 0
			_, _, err := client.Get(context.Background(), "FILE", "")
			var apiErr *APIError
			if !errors.As(err, &apiErr) || apiErr.Status != test.status || apiErr.Reason != test.reason {
				t.Fatalf("lost Google error: %v", err)
			}
			if errors.Is(err, ErrNoAccess) != test.noAccess || !strings.Contains(err.Error(), test.reason) {
				t.Fatalf("misleading error: %v", err)
			}
		})
	}
}

func TestGetWithExpiredSessionReportsExpiry(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "X", Name: "privado", MimeType: folderMIME})
	status := &atomic.Int32{}
	status.Store(http.StatusBadRequest)
	fakeTokenServer(t, status)
	client := NewClient(testCreds, NewTokenSource(testCreds, "RT1"))
	_, _, err := client.Get(context.Background(), "X", "")
	if !errors.Is(err, ErrAuthExpired) {
		t.Fatalf("err = %v", err)
	}
}

func TestGetSendsTheResourceKey(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "K", Name: "viejo", MimeType: folderMIME, Public: true, ResourceKey: "0-abc"})
	client := newTestClient(t, "")
	if _, _, err := client.Get(context.Background(), "K", "0-abc"); err != nil {
		t.Fatal(err)
	}
}

func TestGetWithoutAPIKeyGoesStraightToOAuth(t *testing.T) {
	drive := newFakeDrive(t, &fakeFile{ID: "P", Name: "a.pdf", MimeType: "application/pdf", Public: true})
	fakeTokenServer(t, nil)
	creds := Credentials{ClientID: "CID", ClientSecret: "CSECRET"}
	_, oauth, err := NewClient(creds, NewTokenSource(creds, "RT1")).Get(context.Background(), "P", "")
	if err != nil || !oauth || drive.count("denied:P") != 0 {
		t.Fatalf("oauth = %v, err = %v, denied = %d", oauth, err, drive.count("denied:P"))
	}
}

func TestListFollowsPagination(t *testing.T) {
	newFakeDrive(t,
		&fakeFile{ID: "F", Name: "carpeta", MimeType: folderMIME, Public: true},
		&fakeFile{ID: "a", Name: "1.pdf", MimeType: "application/pdf", Parent: "F", Public: true},
		&fakeFile{ID: "b", Name: "2.pdf", MimeType: "application/pdf", Parent: "F", Public: true},
		&fakeFile{ID: "c", Name: "3.pdf", MimeType: "application/pdf", Parent: "F", Public: true},
		&fakeFile{ID: "d", Name: "borrado.pdf", MimeType: "application/pdf", Parent: "F", Public: true, Trashed: true},
	)
	files, err := newTestClient(t, "").List(context.Background(), "F", "", false)
	if err != nil {
		t.Fatal(err)
	}
	var names []string
	for _, file := range files {
		names = append(names, file.Name)
	}
	if strings.Join(names, ",") != "1.pdf,2.pdf,3.pdf" {
		t.Fatalf("names = %v", names)
	}
}

func readAll(t *testing.T, body io.ReadCloser, err error) string {
	t.Helper()
	if err != nil {
		t.Fatal(err)
	}
	defer body.Close()
	content, err := io.ReadAll(body)
	if err != nil {
		t.Fatal(err)
	}
	return string(content)
}

func TestOpenDownloadsMediaAndRetriesRateLimits(t *testing.T) {
	drive := newFakeDrive(t, &fakeFile{ID: "P", Name: "a.pdf", MimeType: "application/pdf", Content: "%PDF", Public: true, RateLimitOnce: true})
	client := newTestClient(t, "")
	client.retryWait = 0
	body, size, err := client.Open(context.Background(), DriveRef{FileID: "P"})
	if got := readAll(t, body, err); got != "%PDF" {
		t.Fatalf("content = %q", got)
	}
	if size != 0 && size != 4 {
		t.Fatalf("size = %d", size)
	}
	if drive.count("media:P") != 2 {
		t.Fatalf("media hits = %d, want a retry", drive.count("media:P"))
	}
}

func TestOpenExportsNativeFiles(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "S", Name: "notas", MimeType: sheetMIME, Content: "tabla", Public: true})
	body, _, err := newTestClient(t, "").Open(context.Background(), DriveRef{FileID: "S", ExportMIME: xlsxMIME})
	if got := readAll(t, body, err); got != "EXPORT:"+xlsxMIME+":tabla" {
		t.Fatalf("content = %q", got)
	}
}

func TestOpenFallsBackToExportLinksWhenTheExportIsTooLarge(t *testing.T) {
	drive := newFakeDrive(t, &fakeFile{ID: "D", Name: "slides", MimeType: docMIME, Content: "grande", ExportTooLarge: true})
	body, _, err := newTestClient(t, "RT1").Open(context.Background(), DriveRef{FileID: "D", ExportMIME: "application/pdf", UseOAuth: true})
	if got := readAll(t, body, err); got != "LINK:pdf:grande" {
		t.Fatalf("content = %q", got)
	}
	if drive.count("export-link:D") != 1 {
		t.Fatal("export link not used")
	}
}

func TestErrorsNeverContainSecrets(t *testing.T) {
	newFakeDrive(t)
	client := newTestClient(t, "RT1")
	_, _, err := client.Open(context.Background(), DriveRef{FileID: "MISSING", UseOAuth: true})
	if err == nil {
		t.Fatal("expected an error")
	}
	for _, secret := range []string{"KEY", "AT2", "RT1", "CSECRET"} {
		if strings.Contains(err.Error(), secret) {
			t.Fatalf("error leaks %s: %v", secret, err)
		}
	}
	_, _, err = client.Open(context.Background(), DriveRef{FileID: "MISSING"})
	if err == nil || strings.Contains(err.Error(), "KEY") {
		t.Fatalf("err = %v", err)
	}
}

func TestFetcherOpensTheResourcesDriveFile(t *testing.T) {
	newFakeDrive(t, &fakeFile{ID: "P", Name: "a.pdf", MimeType: "application/pdf", Content: "%PDF", Public: true})
	fetcher := Fetcher{Client: newTestClient(t, "")}
	body, _, err := fetcher.Open(context.Background(), moodle.Resource{Drive: &moodle.DriveRef{FileID: "P"}})
	if got := readAll(t, body, err); got != "%PDF" {
		t.Fatalf("content = %q", got)
	}
	if _, _, err := fetcher.Open(context.Background(), moodle.Resource{}); err == nil {
		t.Fatal("opened a Moodle resource through Drive")
	}
}
