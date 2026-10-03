package syncer

import (
	"context"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"time"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

func downloadFile(ctx context.Context, client *moodle.Client, resource moodle.Resource, destination string) (int64, error) {
	downloadURL, err := client.DownloadURL(resource.URL)
	if err != nil {
		return 0, err
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return 0, err
	}
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodGet, downloadURL, nil)
		if err != nil {
			return 0, err
		}
		request.Header.Set("User-Agent", "Scrappy/2 Go")
		response, err := client.HTTPClient().Do(request)
		if err != nil {
			lastErr = redactURLError(err)
		} else {
			finalPath := ""
			if response.Request != nil && response.Request.URL != nil {
				finalPath = strings.ToLower(response.Request.URL.Path)
			}
			if strings.Contains(finalPath, "/login/") {
				response.Body.Close()
				return 0, errors.New("Moodle redirigió al login; el token no autorizó el archivo")
			}
			if response.StatusCode >= 200 && response.StatusCode < 300 {
				size, copyErr := copyAtomically(destination, response.Body, resource.Size)
				response.Body.Close()
				if copyErr == nil {
					return size, nil
				}
				lastErr = copyErr
			} else {
				response.Body.Close()
				lastErr = fmt.Errorf("Moodle respondió HTTP %d", response.StatusCode)
				if response.StatusCode != http.StatusTooManyRequests && response.StatusCode < 500 {
					return 0, lastErr
				}
			}
		}
		if attempt < 2 {
			select {
			case <-ctx.Done():
				return 0, ctx.Err()
			case <-time.After(time.Duration(1<<attempt) * 250 * time.Millisecond):
			}
		}
	}
	return 0, lastErr
}

// fetchFile downloads through a Fetcher with the same atomic write and retry
// policy as Moodle downloads.
func fetchFile(ctx context.Context, fetcher Fetcher, resource moodle.Resource, destination string) (int64, error) {
	if fetcher == nil {
		return 0, errors.New("Google Drive no está disponible en esta ejecución")
	}
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return 0, err
	}
	var lastErr error
	for attempt := 0; attempt < 3; attempt++ {
		if attempt > 0 {
			select {
			case <-ctx.Done():
				return 0, ctx.Err()
			case <-time.After(time.Duration(1<<(attempt-1)) * 250 * time.Millisecond):
			}
		}
		body, size, err := fetcher.Open(ctx, resource)
		if err != nil {
			if ctx.Err() != nil {
				return 0, ctx.Err()
			}
			lastErr = err
			continue
		}
		expected := resource.Size
		if expected <= 0 && size > 0 {
			expected = size
		}
		written, err := copyAtomically(destination, body, expected)
		body.Close()
		if err == nil {
			return written, nil
		}
		if ctx.Err() != nil {
			return 0, ctx.Err()
		}
		lastErr = err
	}
	return 0, lastErr
}

func writeShortcut(destination, rawURL string) (int64, error) {
	parsed, err := url.Parse(rawURL)
	if err != nil || (parsed.Scheme != "http" && parsed.Scheme != "https") {
		return 0, errors.New("URL de enlace inválida")
	}
	content := []byte("[InternetShortcut]\nURL=" + rawURL + "\n")
	if err := atomicWrite(destination, content, 0o644); err != nil {
		return 0, err
	}
	return int64(len(content)), nil
}

func copyAtomically(destination string, source io.Reader, expectedSize int64) (int64, error) {
	directory := filepath.Dir(destination)
	temporary, err := os.CreateTemp(directory, ".scrappy-*.part")
	if err != nil {
		return 0, err
	}
	temporaryName := temporary.Name()
	defer os.Remove(temporaryName)
	size, copyErr := io.Copy(temporary, source)
	closeErr := temporary.Close()
	if copyErr != nil {
		return 0, copyErr
	}
	if closeErr != nil {
		return 0, closeErr
	}
	if expectedSize > 0 && size != expectedSize {
		return 0, fmt.Errorf("tamaño incompleto: esperado %d, recibido %d", expectedSize, size)
	}
	if err := replaceFile(temporaryName, destination); err != nil {
		return 0, err
	}
	return size, nil
}

func atomicWrite(destination string, content []byte, mode os.FileMode) error {
	if err := os.MkdirAll(filepath.Dir(destination), 0o755); err != nil {
		return err
	}
	temporary, err := os.CreateTemp(filepath.Dir(destination), ".scrappy-*.tmp")
	if err != nil {
		return err
	}
	name := temporary.Name()
	defer os.Remove(name)
	if _, err := temporary.Write(content); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Chmod(mode); err != nil {
		temporary.Close()
		return err
	}
	if err := temporary.Close(); err != nil {
		return err
	}
	return replaceFile(name, destination)
}

func replaceFile(source, destination string) error {
	if err := os.Rename(source, destination); err == nil {
		return nil
	} else if runtime.GOOS != "windows" {
		return err
	}
	if err := os.Remove(destination); err != nil && !errors.Is(err, os.ErrNotExist) {
		return err
	}
	return os.Rename(source, destination)
}

// redactURLError drops the query (which carries the Moodle token) from the URL
// that net/http embeds in transport errors, since these reach the UI and report.
func redactURLError(err error) error {
	var urlErr *url.Error
	if !errors.As(err, &urlErr) {
		return err
	}
	if parsed, parseErr := url.Parse(urlErr.URL); parseErr == nil {
		parsed.RawQuery = ""
		urlErr.URL = parsed.String()
	} else {
		urlErr.URL = "(URL omitida)"
	}
	return err
}

// AtomicWrite replaces destination with content without ever leaving a
// half-written file behind.
func AtomicWrite(destination string, content []byte, mode os.FileMode) error {
	return atomicWrite(destination, content, mode)
}
