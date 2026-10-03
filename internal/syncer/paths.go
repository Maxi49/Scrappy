package syncer

import (
	"crypto/sha256"
	"encoding/hex"
	"mime"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"unicode/utf8"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

var invalidFilename = regexp.MustCompile(`[\\/:*?"<>|\x00-\x1f]`)

// planDestinations gives every resource a stable local path. A resource that
// already has a file keeps the path the manifest recorded for it, and new
// collisions are settled by resource ID, so reordering the catalog between runs
// can never point one resource at another resource's file.
func planDestinations(resources []moodle.Resource, manifest Manifest) map[string]string {
	result := make(map[string]string, len(resources))
	claimed := make(map[string]bool, len(resources))
	claim := func(id, relative string) {
		claimed[pathKey(relative)] = true
		result[id] = relative
	}
	natural := make(map[string]string, len(resources))
	for _, resource := range resources {
		natural[resource.ID] = naturalPath(resource)
	}

	for _, resource := range resources {
		if _, done := result[resource.ID]; done {
			continue
		}
		module := manifest.module(resource.CourseID, resource.CourseName, resource.ModuleName, false)
		if module == nil || module.Resources[resource.ID] == nil {
			continue
		}
		recorded := filepath.FromSlash(module.Resources[resource.ID].RelativePath)
		// Only reuse the recorded path while it still matches the resource;
		// a rename or move in Moodle should move the local file too.
		if (pathKey(recorded) == pathKey(natural[resource.ID]) || pathKey(recorded) == pathKey(suffixedPath(natural[resource.ID], resource.ID, 8))) &&
			!claimed[pathKey(recorded)] {
			claim(resource.ID, recorded)
		}
	}

	pending := make([]moodle.Resource, 0, len(resources))
	for _, resource := range resources {
		if _, done := result[resource.ID]; !done {
			pending = append(pending, resource)
		}
	}
	sort.SliceStable(pending, func(i, j int) bool { return pending[i].ID < pending[j].ID })
	for _, resource := range pending {
		if _, done := result[resource.ID]; done {
			continue
		}
		relative := natural[resource.ID]
		for length := 8; claimed[pathKey(relative)]; length *= 2 {
			relative = suffixedPath(natural[resource.ID], resource.ID, length)
			if length >= len(resource.ID) {
				break
			}
		}
		claim(resource.ID, relative)
	}
	return result
}

func naturalPath(resource moodle.Resource) string {
	parts := []string{sanitizeSegment(resource.CourseName, "materia"), sanitizeSegment(resource.ModuleName, "sin_modulo")}
	for _, part := range strings.Split(strings.ReplaceAll(resource.Subfolder, "\\", "/"), "/") {
		if clean := sanitizeSegment(part, ""); clean != "" {
			parts = append(parts, clean)
		}
	}
	filename := sanitizeSegment(resource.Name, "archivo")
	if resource.IsLink() {
		if !strings.EqualFold(filepath.Ext(filename), ".url") {
			filename += ".url"
		}
	} else if filepath.Ext(filename) == "" {
		if extensions, _ := mime.ExtensionsByType(resource.MIME); len(extensions) > 0 {
			filename += extensions[0]
		}
	}
	parts = append(parts, filename)
	return filepath.Join(parts...)
}

// suffixedPath tags a colliding filename with the start of the resource ID.
func suffixedPath(relative, id string, length int) string {
	if length > len(id) {
		length = len(id)
	}
	extension := filepath.Ext(relative)
	return strings.TrimSuffix(relative, extension) + "_" + sanitizeSegment(id[:length], "") + extension
}

func pathKey(relative string) string { return strings.ToLower(filepath.Clean(relative)) }

func sanitizeSegment(value, fallback string) string {
	value = invalidFilename.ReplaceAllString(value, "_")
	value = strings.Join(strings.Fields(value), " ")
	value = strings.TrimRight(strings.TrimSpace(value), ". ")
	if value == "" {
		value = fallback
	}
	base := strings.ToUpper(strings.TrimSuffix(value, filepath.Ext(value)))
	reserved := base == "CON" || base == "PRN" || base == "AUX" || base == "NUL" ||
		(len(base) == 4 && (strings.HasPrefix(base, "COM") || strings.HasPrefix(base, "LPT")) && base[3] >= '1' && base[3] <= '9')
	if reserved {
		value = "_" + value
	}
	for utf8.RuneCountInString(value) > 160 {
		_, size := utf8.DecodeLastRuneInString(value)
		value = value[:len(value)-size]
	}
	return value
}

func fingerprint(resource moodle.Resource) string {
	value := strings.Join([]string{
		resource.ID, string(resource.Type), resource.URL, resource.MIME,
		strconvItoa64(resource.Size), strconvItoa64(resource.Modified),
	}, "\x00")
	hash := sha256.Sum256([]byte(value))
	return hex.EncodeToString(hash[:])
}
