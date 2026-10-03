package syncer

import (
	"crypto/sha256"
	"encoding/hex"
	"mime"
	"path/filepath"
	"regexp"
	"strings"
	"unicode/utf8"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

var invalidFilename = regexp.MustCompile(`[\\/:*?"<>|\x00-\x1f]`)

func planDestinations(resources []moodle.Resource) map[string]string {
	result := make(map[string]string, len(resources))
	claimed := make(map[string]string, len(resources))
	for _, resource := range resources {
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
		relative := filepath.Join(parts...)
		key := strings.ToLower(filepath.Clean(relative))
		if previous, exists := claimed[key]; exists && previous != resource.ID {
			extension := filepath.Ext(filename)
			stem := strings.TrimSuffix(filename, extension)
			short := resource.ID
			if len(short) > 8 {
				short = short[:8]
			}
			parts[len(parts)-1] = stem + "_" + short + extension
			relative = filepath.Join(parts...)
			key = strings.ToLower(filepath.Clean(relative))
		}
		claimed[key] = resource.ID
		result[resource.ID] = relative
	}
	return result
}

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
