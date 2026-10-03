package gdrive

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

var apiBase = "https://www.googleapis.com/drive/v3"

const (
	FolderMIME   = "application/vnd.google-apps.folder"
	shortcutMIME = "application/vnd.google-apps.shortcut"
	fileFields   = "id,name,mimeType,size,modifiedTime,trashed,resourceKey,shortcutDetails"
)

var (
	// ErrPrivate means the API key cannot read the item and no Google account
	// is connected.
	ErrPrivate = errors.New("esta carpeta de Drive es privada; conectá Google en Conexión")
	// ErrNoAccess means neither the API key nor the connected account can read it.
	ErrNoAccess = errors.New("Google Drive no permite acceder a este recurso con la cuenta conectada; verificá el enlace y sus permisos")
)

// File is the Drive metadata Scrappy needs.
type File struct {
	ID              string    `json:"id"`
	Name            string    `json:"name"`
	MimeType        string    `json:"mimeType"`
	Size            int64     `json:"size,string"`
	ModifiedTime    time.Time `json:"modifiedTime"`
	Trashed         bool      `json:"trashed"`
	ResourceKey     string    `json:"resourceKey"`
	ShortcutDetails *struct {
		TargetID       string `json:"targetId"`
		TargetMimeType string `json:"targetMimeType"`
	} `json:"shortcutDetails"`
}

type DriveRef = moodle.DriveRef

// APIError is a Drive error response, reduced to what is safe to show.
type APIError struct {
	Status int
	Reason string
}

func (e *APIError) Error() string {
	detail := fmt.Sprintf("Google Drive respondió HTTP %d", e.Status)
	if e.Reason != "" {
		detail += " (" + e.Reason + ")"
	}
	switch e.Reason {
	case "insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT":
		return detail + ": " + ErrDrivePermission.Error()
	case "accessNotConfigured", "SERVICE_DISABLED":
		return detail + ": la API de Drive no está habilitada para el proyecto de Google de esta aplicación"
	case "domainPolicy":
		return detail + ": una política de la organización restringe el acceso de la aplicación"
	}
	return detail
}

func (e *APIError) denied() bool {
	return e.Status == http.StatusForbidden || e.Status == http.StatusNotFound
}

func (e *APIError) fileAccessDenied() bool {
	return e.Status == http.StatusNotFound || (e.Status == http.StatusForbidden &&
		(e.Reason == "insufficientFilePermissions" || e.Reason == "appNotAuthorizedToFile"))
}

func (e *APIError) retryable() bool {
	return e.Status == http.StatusTooManyRequests || e.Status >= 500 ||
		e.Reason == "rateLimitExceeded" || e.Reason == "userRateLimitExceeded"
}

type Client struct {
	creds     Credentials
	tokens    *TokenSource
	http      *http.Client
	retryWait time.Duration
}

func NewClient(creds Credentials, tokens *TokenSource) *Client {
	return &Client{creds: creds, tokens: tokens, http: &http.Client{}, retryWait: 500 * time.Millisecond}
}

// Enabled reports whether this build can reach Drive at all.
func (c *Client) Enabled() bool { return c.creds.APIKey != "" || c.creds.canLogin() }

// Get reads a link's root item, trying the API key first and the student's
// account second. It reports which one worked so the whole tree reuses it.
func (c *Client) Get(ctx context.Context, id, resourceKey string) (File, bool, error) {
	var file File
	get := func(oauth bool) error {
		return c.getJSON(ctx, "/files/"+url.PathEscape(id), url.Values{"fields": {fileFields}}, id, resourceKey, oauth, &file)
	}
	if c.creds.APIKey != "" {
		err := get(false)
		var apiErr *APIError
		if err == nil || !errors.As(err, &apiErr) || !apiErr.denied() {
			return file, false, err
		}
		if !c.tokens.HasSession() {
			if apiErr.fileAccessDenied() {
				return file, false, fmt.Errorf("%w: %w", ErrPrivate, apiErr)
			}
			return file, false, err
		}
	}
	err := get(true)
	var apiErr *APIError
	if errors.As(err, &apiErr) && apiErr.fileAccessDenied() {
		return file, true, fmt.Errorf("%w: %w", ErrNoAccess, apiErr)
	}
	if errors.Is(err, ErrNoSession) {
		return file, true, ErrPrivate
	}
	return file, true, err
}

// List returns the folder's children that are not in the trash.
func (c *Client) List(ctx context.Context, folderID, resourceKey string, oauth bool) ([]File, error) {
	var files []File
	pageToken := ""
	for {
		query := url.Values{
			"q":                         {fmt.Sprintf("'%s' in parents and trashed = false", folderID)},
			"fields":                    {"nextPageToken,files(" + fileFields + ")"},
			"pageSize":                  {"1000"},
			"includeItemsFromAllDrives": {"true"},
		}
		if pageToken != "" {
			query.Set("pageToken", pageToken)
		}
		var page struct {
			Files         []File `json:"files"`
			NextPageToken string `json:"nextPageToken"`
		}
		if err := c.getJSON(ctx, "/files", query, folderID, resourceKey, oauth, &page); err != nil {
			return nil, err
		}
		files = append(files, page.Files...)
		if page.NextPageToken == "" {
			return files, nil
		}
		pageToken = page.NextPageToken
	}
}

// Open starts the download of a regular file, or the export of a Google
// Docs/Sheets/Slides file. Exports over Drive's 10 MB API limit retry through
// the file's exportLinks, the URLs Drive's own download menu uses.
func (c *Client) Open(ctx context.Context, ref DriveRef) (io.ReadCloser, int64, error) {
	path := "/files/" + url.PathEscape(ref.FileID)
	if ref.ExportMIME == "" {
		response, err := c.do(ctx, apiBase+path, url.Values{"alt": {"media"}}, ref.FileID, ref.ResourceKey, ref.UseOAuth)
		if err != nil {
			return nil, 0, err
		}
		return response.Body, response.ContentLength, nil
	}
	response, err := c.do(ctx, apiBase+path+"/export", url.Values{"mimeType": {ref.ExportMIME}}, ref.FileID, ref.ResourceKey, ref.UseOAuth)
	var apiErr *APIError
	if err == nil {
		return response.Body, 0, nil
	}
	if !errors.As(err, &apiErr) || apiErr.Reason != "exportSizeLimitExceeded" {
		return nil, 0, err
	}
	var links struct {
		ExportLinks map[string]string `json:"exportLinks"`
	}
	if err := c.getJSON(ctx, path, url.Values{"fields": {"exportLinks"}}, ref.FileID, ref.ResourceKey, ref.UseOAuth, &links); err != nil {
		return nil, 0, err
	}
	link := links.ExportLinks[ref.ExportMIME]
	if link == "" {
		return nil, 0, err
	}
	response, err = c.do(ctx, link, nil, ref.FileID, ref.ResourceKey, ref.UseOAuth)
	if err != nil {
		return nil, 0, err
	}
	return response.Body, 0, nil
}

func (c *Client) getJSON(ctx context.Context, path string, query url.Values, id, resourceKey string, oauth bool, target any) error {
	response, err := c.do(ctx, apiBase+path, query, id, resourceKey, oauth)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if err := json.NewDecoder(response.Body).Decode(target); err != nil {
		return errors.New("Google Drive devolvió una respuesta inválida")
	}
	return nil
}

// do sends an authenticated GET and retries quota and server errors. On
// success the caller owns the body. Errors never carry the URL, which holds
// the API key, or the bearer token.
func (c *Client) do(ctx context.Context, endpoint string, query url.Values, id, resourceKey string, oauth bool) (*http.Response, error) {
	target, err := url.Parse(endpoint)
	if err != nil {
		return nil, errors.New("URL de Google Drive inválida")
	}
	values := target.Query()
	for key, list := range query {
		values[key] = list
	}
	if strings.HasPrefix(endpoint, apiBase) {
		values.Set("supportsAllDrives", "true")
	}
	if !oauth && c.creds.APIKey != "" && strings.HasPrefix(endpoint, apiBase) {
		values.Set("key", c.creds.APIKey)
	}
	target.RawQuery = values.Encode()

	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(time.Duration(1<<(attempt-1)) * c.retryWait):
			}
		}
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, target.String(), nil)
		if err != nil {
			return nil, err
		}
		request.Header.Set("User-Agent", "Scrappy/2 Go")
		if resourceKey != "" {
			request.Header.Set("X-Goog-Drive-Resource-Keys", id+"/"+resourceKey)
		}
		if oauth {
			token, err := c.tokens.Token(ctx)
			if err != nil {
				return nil, err
			}
			request.Header.Set("Authorization", "Bearer "+token)
		}
		response, err := c.http.Do(request)
		if err != nil {
			if ctx.Err() != nil {
				return nil, ctx.Err()
			}
			lastErr = errors.New("no se pudo contactar a Google Drive")
			continue
		}
		if response.StatusCode >= 200 && response.StatusCode < 300 {
			return response, nil
		}
		apiErr := readAPIError(response)
		if !apiErr.retryable() {
			return nil, apiErr
		}
		lastErr = apiErr
	}
	return nil, lastErr
}

func readAPIError(response *http.Response) *APIError {
	defer response.Body.Close()
	var payload struct {
		Error struct {
			Errors []struct {
				Reason string `json:"reason"`
			} `json:"errors"`
			Status string `json:"status"`
		} `json:"error"`
	}
	apiErr := &APIError{Status: response.StatusCode}
	if json.NewDecoder(io.LimitReader(response.Body, 1<<16)).Decode(&payload) == nil {
		if len(payload.Error.Errors) > 0 {
			apiErr.Reason = payload.Error.Errors[0].Reason
		} else {
			apiErr.Reason = payload.Error.Status
		}
	}
	return apiErr
}

// getAs reads an item with a fixed credential, for shortcuts inside a tree
// whose credential is already known.
func (c *Client) getAs(ctx context.Context, id, resourceKey string, oauth bool) (File, error) {
	var file File
	err := c.getJSON(ctx, "/files/"+url.PathEscape(id), url.Values{"fields": {fileFields}}, id, resourceKey, oauth, &file)
	return file, err
}
