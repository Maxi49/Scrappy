// Package gdrive downloads the Google Drive content that Moodle links to.
package gdrive

import (
	"net/url"
	"regexp"
	"strings"
)

// Link is a Drive file or folder referenced from Moodle.
type Link struct {
	ID          string
	Folder      bool
	ResourceKey string
}

var (
	folderPath = regexp.MustCompile(`^/drive/(?:u/\d+/)?folders/([\w-]+)`)
	filePath   = regexp.MustCompile(`^/file/(?:u/\d+/)?d/([\w-]+)`)
	docsPath   = regexp.MustCompile(`^/(?:document|spreadsheets|presentation|drawings)/(?:u/\d+/)?d/([\w-]+)`)
)

// ParseLink extracts the Drive ID from the URL shapes professors paste into
// Moodle. Anything else (Forms, "My Drive", other hosts) is not downloadable.
func ParseLink(raw string) (Link, bool) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil {
		return Link{}, false
	}
	host := strings.ToLower(parsed.Hostname())
	query := parsed.Query()
	link := Link{ResourceKey: query.Get("resourcekey")}
	switch host {
	case "drive.google.com":
		if match := folderPath.FindStringSubmatch(parsed.Path); match != nil {
			link.ID, link.Folder = match[1], true
		} else if match := filePath.FindStringSubmatch(parsed.Path); match != nil {
			link.ID = match[1]
		} else if parsed.Path == "/open" || parsed.Path == "/uc" {
			link.ID = query.Get("id")
		}
	case "docs.google.com":
		if match := docsPath.FindStringSubmatch(parsed.Path); match != nil {
			link.ID = match[1]
		}
	}
	if link.ID == "" {
		return Link{}, false
	}
	return link, true
}
