package gdrive

import (
	"context"
	"errors"
	"io"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

// Fetcher adapts Client to syncer.Fetcher.
type Fetcher struct{ Client *Client }

func (f Fetcher) Open(ctx context.Context, resource moodle.Resource) (io.ReadCloser, int64, error) {
	if resource.Drive == nil {
		return nil, 0, errors.New("el recurso no viene de Google Drive")
	}
	return f.Client.Open(ctx, *resource.Drive)
}

// UseEndpoints points the package at other Drive and OAuth servers and returns
// a function that restores the real ones. Tests outside this package use it.
func UseEndpoints(drive, token string) (restore func()) {
	previousAPI, previousToken := apiBase, tokenURL
	apiBase, tokenURL = drive, token
	return func() { apiBase, tokenURL = previousAPI, previousToken }
}
