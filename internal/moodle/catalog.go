package moodle

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"html"
	"net/url"
	"path"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
)

type ProgressFunc func(string)

type moduleContext struct {
	CourseID     int
	CourseName   string
	SectionName  string
	ActivityName string
	CourseModule int
	ModName      string
	Accessible   bool
}

type catalogBuilder struct {
	baseURL     *url.URL
	resources   map[string]Resource
	moduleByID  map[int]moduleContext
	courseByID  map[int]Course
	moduleKinds map[string]bool
	diagnostics Diagnostics
}

func newCatalogBuilder(baseURL *url.URL, courses []Course) *catalogBuilder {
	courseByID := make(map[int]Course, len(courses))
	for _, course := range courses {
		courseByID[course.ID] = course
	}
	return &catalogBuilder{
		baseURL:     baseURL,
		resources:   make(map[string]Resource),
		moduleByID:  make(map[int]moduleContext),
		courseByID:  courseByID,
		moduleKinds: make(map[string]bool),
		diagnostics: Diagnostics{
			ContentItemsByType:             make(map[string]int),
			ResourcesBySource:              make(map[string]int),
			ActivitiesWithoutDirectContent: make(map[string]int),
		},
	}
}

// ListCourses authenticates when needed and returns all courses enrolled for
// the current user. Credentials never leave this process after authentication.
func ListCourses(ctx context.Context, client *Client, username, password string) ([]Course, SiteInfo, error) {
	if client.Token() == "" {
		if err := client.Authenticate(ctx, username, password); err != nil {
			return nil, SiteInfo{}, err
		}
	}
	info, err := client.SiteInfo(ctx)
	if err != nil {
		return nil, SiteInfo{}, err
	}
	courses, err := client.EnrolledCourses(ctx, info.UserID)
	return courses, info, err
}

// Discover combines core_course_get_contents with module-specific APIs.
// Moodle intentionally returns only a partial view from the core endpoint;
// introfiles/contentfiles from assignments, labels, pages, and similar
// activities are recovered through the complementary endpoints.
func Discover(ctx context.Context, client *Client, courses []Course, info SiteInfo, progress ProgressFunc) (Catalog, error) {
	builder := newCatalogBuilder(client.baseURL, courses)
	type coreResult struct {
		course   Course
		sections []courseSection
		err      error
	}
	results := make(chan coreResult, len(courses))
	semaphore := make(chan struct{}, 8)
	var wait sync.WaitGroup
	for _, course := range courses {
		course := course
		wait.Add(1)
		go func() {
			defer wait.Done()
			select {
			case semaphore <- struct{}{}:
				defer func() { <-semaphore }()
			case <-ctx.Done():
				results <- coreResult{course: course, err: ctx.Err()}
				return
			}
			sections, err := client.CourseContents(ctx, course.ID)
			results <- coreResult{course: course, sections: sections, err: err}
		}()
	}
	wait.Wait()
	close(results)

	// A single broken course must not block the rest of the selection: its
	// error is reported and the healthy courses are still synchronised.
	var analysed []Course
	for result := range results {
		if result.err != nil {
			builder.diagnostics.CourseErrors = append(builder.diagnostics.CourseErrors, CourseError{
				Course: result.course.Name, Error: result.err.Error(),
			})
			if progress != nil {
				progress(fmt.Sprintf("✗ %s: %v", result.course.Name, result.err))
			}
			continue
		}
		analysed = append(analysed, result.course)
		builder.addCoreCourse(result.course, result.sections)
		if progress != nil {
			progress(fmt.Sprintf("✓ %s: contenido base analizado", result.course.Name))
		}
	}
	sort.Slice(builder.diagnostics.CourseErrors, func(i, j int) bool {
		return builder.diagnostics.CourseErrors[i].Course < builder.diagnostics.CourseErrors[j].Course
	})
	if len(analysed) == 0 && len(courses) > 0 {
		messages := make([]string, 0, len(builder.diagnostics.CourseErrors))
		for _, failure := range builder.diagnostics.CourseErrors {
			messages = append(messages, failure.Course+": "+failure.Error)
		}
		return Catalog{}, fmt.Errorf("no se pudo analizar ninguna materia: %s", strings.Join(messages, "; "))
	}
	sort.Slice(analysed, func(i, j int) bool { return analysed[i].ID < analysed[j].ID })

	available := make(map[string]bool, len(info.Functions))
	for _, fn := range info.Functions {
		available[fn.Name] = true
	}

	type supplementResult struct {
		function string
		value    any
		err      error
	}
	functions := builder.supplementFunctions(available)
	supplements := make(chan supplementResult, len(functions))
	for _, function := range functions {
		function := function
		wait.Add(1)
		go func() {
			defer wait.Done()
			value, err := client.CallRaw(ctx, function, CourseIDsParams(analysed))
			supplements <- supplementResult{function: function, value: value, err: err}
		}()
	}
	wait.Wait()
	close(supplements)
	for result := range supplements {
		if result.err != nil {
			builder.diagnostics.Warnings = append(builder.diagnostics.Warnings, result.err.Error())
			continue
		}
		builder.walkSupplement(result.value, recordContext{}, result.function)
	}

	resources := make([]Resource, 0, len(builder.resources))
	for _, resource := range builder.resources {
		resources = append(resources, resource)
		if resource.Accessible {
			builder.diagnostics.AccessibleResources++
		} else {
			builder.diagnostics.InaccessibleResources++
		}
	}
	sort.Slice(resources, func(i, j int) bool {
		a, b := resources[i], resources[j]
		if a.CourseName != b.CourseName {
			return a.CourseName < b.CourseName
		}
		if a.ModuleName != b.ModuleName {
			return a.ModuleName < b.ModuleName
		}
		if a.Subfolder != b.Subfolder {
			return a.Subfolder < b.Subfolder
		}
		if a.Name != b.Name {
			return a.Name < b.Name
		}
		return a.ID < b.ID
	})
	sort.Strings(builder.diagnostics.Warnings)
	return Catalog{Resources: resources, Diagnostics: builder.diagnostics}, nil
}

func (b *catalogBuilder) addCoreCourse(course Course, sections []courseSection) {
	for _, section := range sections {
		b.diagnostics.Sections++
		sectionName := strings.TrimSpace(section.Name)
		if sectionName == "" {
			sectionName = fmt.Sprintf("Sección %d", section.Section)
		}
		b.addSectionDriveLinks(moduleContext{
			CourseID: course.ID, CourseName: course.Name, SectionName: sectionName, Accessible: true,
		}, section.Summary)
		for _, module := range section.Modules {
			b.diagnostics.Activities++
			kind := strings.ToLower(strings.TrimSpace(module.ModName))
			b.moduleKinds[kind] = true
			accessible := flexibleBool(module.UserVisible, true)
			if !accessible {
				b.diagnostics.InaccessibleModules++
			}
			ctx := moduleContext{
				CourseID: course.ID, CourseName: course.Name, SectionName: sectionName,
				ActivityName: strings.TrimSpace(module.Name), CourseModule: module.ID,
				ModName: kind, Accessible: accessible,
			}
			b.moduleByID[module.ID] = ctx

			if len(module.Contents) == 0 {
				b.diagnostics.ActivitiesWithoutDirectContent[kind]++
			}
			for _, item := range module.Contents {
				itemType := strings.ToLower(strings.TrimSpace(item.Type))
				if itemType == "" {
					itemType = "unknown"
				}
				b.diagnostics.ContentItemsByType[itemType]++
				switch {
				case itemType == "file" || looksLikeMoodleFile(item.FileURL):
					b.addFile(ctx, item, "core_course_get_contents")
				case itemType == "url" || strings.TrimSpace(item.FileURL) != "":
					b.addLink(ctx, module.Name, item.FileURL, "core_course_get_contents")
				}
			}
			b.addHTMLLinks(ctx, module.Description, "core_course_get_contents")
			if kind == "url" && len(module.Contents) == 0 && module.URL != "" && accessible {
				b.addLink(ctx, module.Name, module.URL, "core_course_get_contents")
			}
		}
	}
}

func (b *catalogBuilder) addFile(ctx moduleContext, item contentItem, source string) {
	rawURL := b.resolveURL(item.FileURL)
	if rawURL == "" {
		return
	}
	name := strings.TrimSpace(item.Filename)
	if name == "" {
		parsed, _ := url.Parse(rawURL)
		name = path.Base(parsed.Path)
	}
	if name == "" || name == "." || name == "/" {
		name = strings.TrimSpace(ctx.ActivityName)
	}
	subfolder := cleanMoodleFolder(item.Filepath)
	identity, ok := storedFileKey(rawURL)
	if !ok {
		identity = fmt.Sprintf("file|%d|%d|%s|%s", ctx.CourseID, ctx.CourseModule, strings.ToLower(subfolder), strings.ToLower(name))
	}
	resource := Resource{
		ID: stableID(identity), CourseID: ctx.CourseID, CourseName: ctx.CourseName,
		ModuleName: ctx.SectionName, ActivityName: ctx.ActivityName, CourseModule: ctx.CourseModule,
		Name: name, URL: stripToken(rawURL), Type: classifyFile(name), Subfolder: subfolder,
		MIME: item.MIME, Size: item.Filesize, Modified: item.TimeModified, Source: source,
		Accessible: ctx.Accessible, embedded: item.embedded,
	}
	b.addResource(identity, resource)
}

func (b *catalogBuilder) addLink(ctx moduleContext, name, rawURL, source string) {
	rawURL = b.resolveURL(rawURL)
	if rawURL == "" || !isHTTP(rawURL) {
		return
	}
	if looksLikeMoodleFile(rawURL) {
		b.addFile(ctx, contentItem{Filename: path.Base(mustURLPath(rawURL)), FileURL: rawURL, embedded: true}, source)
		return
	}
	name = strings.TrimSpace(name)
	if name == "" {
		name = strings.TrimSpace(ctx.ActivityName)
	}
	if name == "" {
		name = "Enlace"
	}
	canonical := canonicalURL(rawURL)
	identity := fmt.Sprintf("link|%d|%d|%s", ctx.CourseID, ctx.CourseModule, canonical)
	resource := Resource{
		ID: stableID(identity), CourseID: ctx.CourseID, CourseName: ctx.CourseName,
		ModuleName: ctx.SectionName, ActivityName: ctx.ActivityName, CourseModule: ctx.CourseModule,
		Name: name, URL: stripToken(rawURL), Type: classifyLink(rawURL), Source: source,
		Accessible: ctx.Accessible,
	}
	b.addResource(identity, resource)
}

func (b *catalogBuilder) addResource(identity string, resource Resource) {
	if previous, exists := b.resources[identity]; exists {
		b.diagnostics.DuplicateResources++
		if previous.embedded && !resource.embedded {
			// Keep the owning activity's placement and metadata.
			b.diagnostics.ResourcesBySource[previous.Source]--
			b.diagnostics.ResourcesBySource[resource.Source]++
			previous, resource = resource, previous
		}
		if !previous.Accessible && resource.Accessible {
			previous.Accessible = true
		}
		if previous.Size == 0 && resource.Size > 0 {
			previous.Size = resource.Size
		}
		if previous.Modified < resource.Modified {
			previous.Modified = resource.Modified
		}
		if previous.MIME == "" {
			previous.MIME = resource.MIME
		}
		b.resources[identity] = previous
		return
	}
	b.resources[identity] = resource
	b.diagnostics.ResourcesBySource[resource.Source]++
}

var supplementalByModule = map[string]string{
	"assign":          "mod_assign_get_assignments",
	"bigbluebuttonbn": "mod_bigbluebuttonbn_get_bigbluebuttonbns_by_courses",
	"book":            "mod_book_get_books_by_courses",
	"choice":          "mod_choice_get_choices_by_courses",
	"data":            "mod_data_get_databases_by_courses",
	"feedback":        "mod_feedback_get_feedbacks_by_courses",
	"folder":          "mod_folder_get_folders_by_courses",
	"forum":           "mod_forum_get_forums_by_courses",
	"glossary":        "mod_glossary_get_glossaries_by_courses",
	"h5pactivity":     "mod_h5pactivity_get_h5pactivities_by_courses",
	"imscp":           "mod_imscp_get_imscps_by_courses",
	"label":           "mod_label_get_labels_by_courses",
	"lesson":          "mod_lesson_get_lessons_by_courses",
	"lti":             "mod_lti_get_ltis_by_courses",
	"page":            "mod_page_get_pages_by_courses",
	"questionnaire":   "mod_questionnaire_get_questionnaires_by_courses",
	"quiz":            "mod_quiz_get_quizzes_by_courses",
	"resource":        "mod_resource_get_resources_by_courses",
	"scorm":           "mod_scorm_get_scorms_by_courses",
	"url":             "mod_url_get_urls_by_courses",
	"wiki":            "mod_wiki_get_wikis_by_courses",
	"workshop":        "mod_workshop_get_workshops_by_courses",
}

func (b *catalogBuilder) supplementFunctions(available map[string]bool) []string {
	seen := make(map[string]bool)
	var functions []string
	for module := range b.moduleKinds {
		function := supplementalByModule[module]
		if function != "" && available[function] && !seen[function] {
			seen[function] = true
			functions = append(functions, function)
		}
	}
	sort.Strings(functions)
	return functions
}

type recordContext struct {
	CourseID     int
	CourseModule int
	Name         string
}

func (b *catalogBuilder) walkSupplement(value any, inherited recordContext, source string) {
	switch typed := value.(type) {
	case []any:
		for _, child := range typed {
			b.walkSupplement(child, inherited, source)
		}
	case map[string]any:
		current := inherited
		if id := firstInt(typed, "course", "courseid"); id != 0 {
			current.CourseID = id
		}
		if id := firstInt(typed, "coursemodule", "coursemoduleid", "cmid"); id != 0 {
			current.CourseModule = id
		}
		if name := stringValue(typed["name"]); name != "" {
			current.Name = name
		}

		ctx := b.contextFor(current)
		fileURL := stringValue(typed["fileurl"])
		filename := stringValue(typed["filename"])
		if fileURL != "" && filename != "" && ctx.CourseID != 0 {
			b.addFile(ctx, contentItem{
				Type: "file", Filename: filename, Filepath: stringValue(typed["filepath"]),
				Filesize: int64Value(typed["filesize"]), FileURL: fileURL,
				MIME: stringValue(typed["mimetype"]), TimeModified: int64Value(typed["timemodified"]),
			}, source)
		}
		if external := stringValue(typed["externalurl"]); external != "" && ctx.CourseID != 0 {
			b.addLink(ctx, current.Name, external, source)
		}
		for _, field := range []string{"intro", "content", "description"} {
			if body := stringValue(typed[field]); body != "" && ctx.CourseID != 0 {
				b.addHTMLLinks(ctx, body, source)
			}
		}
		for key, child := range typed {
			if key == "fileurl" || key == "filename" || key == "externalurl" || key == "intro" || key == "content" || key == "description" {
				continue
			}
			b.walkSupplement(child, current, source)
		}
	}
}

func (b *catalogBuilder) contextFor(record recordContext) moduleContext {
	if module, ok := b.moduleByID[record.CourseModule]; ok {
		return module
	}
	course := b.courseByID[record.CourseID]
	name := strings.TrimSpace(record.Name)
	return moduleContext{
		CourseID: record.CourseID, CourseName: course.Name, SectionName: "Contenido general",
		ActivityName: name, CourseModule: record.CourseModule, Accessible: true,
	}
}

var linkAttribute = regexp.MustCompile(`(?is)<(?:a|img|source)\b[^>]*\b(?:href|src)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))`)

func (b *catalogBuilder) addHTMLLinks(ctx moduleContext, body, source string) {
	for _, match := range linkAttribute.FindAllStringSubmatch(body, -1) {
		raw := ""
		for index := 1; index < len(match); index++ {
			if match[index] != "" {
				raw = html.UnescapeString(strings.TrimSpace(match[index]))
				break
			}
		}
		if raw == "" {
			continue
		}
		resolved := b.resolveURL(raw)
		if !isHTTP(resolved) {
			continue
		}
		if looksLikeMoodleFile(resolved) {
			name := path.Base(mustURLPath(resolved))
			b.addFile(ctx, contentItem{Filename: name, FileURL: resolved, embedded: true}, source)
			continue
		}
		parsed, _ := url.Parse(resolved)
		if parsed != nil && !strings.EqualFold(parsed.Hostname(), b.baseURL.Hostname()) {
			b.addLink(ctx, ctx.ActivityName, resolved, source)
		}
	}
}

var (
	anchorTag  = regexp.MustCompile(`(?is)<a\b([^>]*)>(.*?)</a>`)
	hrefValue  = regexp.MustCompile(`(?is)\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))`)
	titleValue = regexp.MustCompile(`(?is)\btitle\s*=\s*(?:"([^"]*)"|'([^']*)')`)
	htmlTag    = regexp.MustCompile(`(?s)<[^>]*>`)
)

// addSectionDriveLinks takes the Google Drive links professors put in a
// section's description, named after the link text. Other links and images in
// those descriptions are decoration and stay out of the catalog.
func (b *catalogBuilder) addSectionDriveLinks(ctx moduleContext, summary string) {
	for _, anchor := range anchorTag.FindAllStringSubmatch(summary, -1) {
		raw := firstGroup(hrefValue.FindStringSubmatch(anchor[1]))
		resolved := b.resolveURL(html.UnescapeString(strings.TrimSpace(raw)))
		if !isHTTP(resolved) || classifyLink(resolved) != ResourceGoogle {
			continue
		}
		name := strings.Join(strings.Fields(html.UnescapeString(htmlTag.ReplaceAllString(anchor[2], " "))), " ")
		if name == "" {
			name = strings.TrimSpace(html.UnescapeString(firstGroup(titleValue.FindStringSubmatch(anchor[1]))))
		}
		if name == "" {
			name = "Google Drive"
		}
		b.addLink(ctx, name, resolved, "section_summary")
	}
}

func firstGroup(match []string) string {
	for index := 1; index < len(match); index++ {
		if match[index] != "" {
			return match[index]
		}
	}
	return ""
}

func (b *catalogBuilder) resolveURL(raw string) string {
	raw = strings.TrimSpace(html.UnescapeString(raw))
	if raw == "" || strings.HasPrefix(raw, "@@PLUGINFILE@@") {
		return ""
	}
	parsed, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	return b.baseURL.ResolveReference(parsed).String()
}

// ClassifyFile picks the resource type from the file extension.
func ClassifyFile(filename string) ResourceType { return classifyFile(filename) }

func classifyFile(filename string) ResourceType {
	lower := strings.ToLower(filename)
	switch path.Ext(lower) {
	case ".pdf":
		return ResourcePDF
	case ".ppt", ".pptx":
		return ResourcePowerPoint
	case ".doc", ".docx":
		return ResourceWord
	default:
		return ResourceFile
	}
}

func classifyLink(raw string) ResourceType {
	lower := strings.ToLower(raw)
	if strings.Contains(lower, "drive.google.com") || strings.Contains(lower, "docs.google.com") {
		return ResourceGoogle
	}
	if strings.Contains(lower, "youtube.com") || strings.Contains(lower, "youtu.be") {
		return ResourceYouTube
	}
	return ResourceLink
}

func flexibleBool(value any, fallback bool) bool {
	switch typed := value.(type) {
	case nil:
		return fallback
	case bool:
		return typed
	case float64:
		return typed != 0
	case string:
		typed = strings.ToLower(strings.TrimSpace(typed))
		return typed == "1" || typed == "true" || typed == "yes"
	default:
		return fallback
	}
}

// StableID derives a resource ID that survives catalog reordering.
func StableID(identity string) string { return stableID(identity) }

func stableID(identity string) string {
	hash := sha256.Sum256([]byte(identity))
	return hex.EncodeToString(hash[:])
}

func cleanMoodleFolder(raw string) string {
	parts := strings.Split(strings.ReplaceAll(raw, "\\", "/"), "/")
	clean := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" || part == "." || part == ".." {
			continue
		}
		clean = append(clean, part)
	}
	return strings.Join(clean, "/")
}

// storedFileKey identifies the Moodle stored file behind a pluginfile URL:
// context, component, file area, item id, and path. The browser, Web Services
// and token endpoints all map to the same key, as do mod_resource URLs whose
// item id slot carries a cache-busting revision (core_course_get_contents
// reports the revision, mod_resource_get_resources_by_courses reports 0).
func storedFileKey(raw string) (string, bool) {
	parsed, err := url.Parse(raw)
	if err != nil {
		return "", false
	}
	var segments []string
	if index := strings.Index(parsed.Path, "/tokenpluginfile.php/"); index >= 0 {
		segments = strings.Split(strings.Trim(parsed.Path[index+len("/tokenpluginfile.php/"):], "/"), "/")
		if len(segments) > 0 {
			segments = segments[1:] // the per-user file token
		}
	} else if index := strings.Index(parsed.Path, "/pluginfile.php/"); index >= 0 {
		segments = strings.Split(strings.Trim(parsed.Path[index+len("/pluginfile.php/"):], "/"), "/")
	}
	if len(segments) < 2 {
		return "", false
	}
	if len(segments) >= 5 && segments[1] == "mod_resource" && segments[2] == "content" {
		segments = append(append([]string{}, segments[:3]...), segments[4:]...)
	}
	return "file|" + strings.Join(segments, "/"), true
}

func looksLikeMoodleFile(raw string) bool {
	lower := strings.ToLower(raw)
	return strings.Contains(lower, "/pluginfile.php/") || strings.Contains(lower, "/tokenpluginfile.php/")
}

func isHTTP(raw string) bool {
	parsed, err := url.Parse(raw)
	return err == nil && (parsed.Scheme == "http" || parsed.Scheme == "https") && parsed.Host != ""
}

func stripToken(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return raw
	}
	if !looksLikeMoodleFile(raw) {
		return raw
	}
	query := parsed.Query()
	query.Del("token")
	query.Del("wstoken")
	parsed.RawQuery = query.Encode()
	return parsed.String()
}

func canonicalURL(raw string) string {
	parsed, err := url.Parse(stripToken(raw))
	if err != nil {
		return raw
	}
	if looksLikeMoodleFile(raw) {
		query := parsed.Query()
		query.Del("forcedownload")
		parsed.RawQuery = query.Encode()
	}
	if classifyLink(raw) == ResourceGoogle {
		// usp only records where a Drive link was shared from.
		query := parsed.Query()
		query.Del("usp")
		parsed.RawQuery = query.Encode()
	}
	parsed.Fragment = ""
	return parsed.String()
}

func mustURLPath(raw string) string {
	parsed, err := url.Parse(raw)
	if err != nil {
		return ""
	}
	return parsed.Path
}

func firstInt(values map[string]any, keys ...string) int {
	for _, key := range keys {
		if value := intValue(values[key]); value != 0 {
			return value
		}
	}
	return 0
}

func intValue(value any) int {
	switch typed := value.(type) {
	case float64:
		return int(typed)
	case string:
		result, _ := strconv.Atoi(typed)
		return result
	default:
		return 0
	}
}

func int64Value(value any) int64 {
	switch typed := value.(type) {
	case float64:
		return int64(typed)
	case string:
		result, _ := strconv.ParseInt(typed, 10, 64)
		return result
	default:
		return 0
	}
}

func stringValue(value any) string {
	if typed, ok := value.(string); ok {
		return strings.TrimSpace(typed)
	}
	return ""
}
