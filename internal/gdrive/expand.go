package gdrive

import (
	"context"
	"fmt"
	"path"
	"sort"
	"strings"
	"time"

	"github.com/Maxi49/Scrappy/internal/moodle"
)

const Source = "google_drive"

// Native Google files are exported: documents and slides to PDF, sheets to
// Excel. Other native types (Forms, Sites…) cannot be exported and are kept as
// shortcuts.
var exports = map[string]struct{ mime, extension string }{
	"application/vnd.google-apps.document":     {"application/pdf", ".pdf"},
	"application/vnd.google-apps.presentation": {"application/pdf", ".pdf"},
	"application/vnd.google-apps.drawing":      {"application/pdf", ".pdf"},
	"application/vnd.google-apps.spreadsheet":  {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx"},
}

type ExpandOptions struct {
	Selection Selection
	// Previous is the last saved tree; folders this run does not list keep
	// their children from it.
	Previous Tree
	// Full lists every link completely (the Drive panel's scan). A sync only
	// lists what the selection can reach.
	Full     bool
	Progress moodle.ProgressFunc
}

// RootFailure is a Drive link the student selected but Scrappy cannot read.
type RootFailure struct {
	Course   string
	Module   string
	Resource string
	Error    string
}

type Expansion struct {
	Catalog    moodle.Catalog
	Tree       Tree
	Failures   []RootFailure
	Unreviewed int
}

func rootKey(courseID int, module, id string) string {
	return fmt.Sprintf("%d|%s|%s", courseID, module, id)
}

// Expand adds the selected files behind every Drive link in the catalog and
// returns the refreshed tree for the Drive panel. Only cancellation is an
// error; unreadable links become failures or tree errors.
func Expand(ctx context.Context, client *Client, catalog moodle.Catalog, options ExpandOptions) (Expansion, error) {
	result := Expansion{Catalog: catalog, Tree: Tree{ScannedAt: time.Now().UTC().Format(time.RFC3339)}}
	type driveLink struct {
		resource moodle.Resource
		link     Link
	}
	var links []driveLink
	for _, resource := range catalog.Resources {
		if resource.Type != moodle.ResourceGoogle || !resource.Accessible {
			continue
		}
		if link, ok := ParseLink(resource.URL); ok {
			links = append(links, driveLink{resource, link})
		}
	}
	if len(links) == 0 {
		return result, nil
	}
	if !client.Enabled() {
		result.Catalog.Diagnostics.Warnings = append(append([]string(nil), catalog.Diagnostics.Warnings...),
			"Google Drive no está configurado en esta versión; los links de Drive se guardan solo como accesos directos.")
		return result, nil
	}

	resources := append([]moodle.Resource(nil), catalog.Resources...)
	bySource := make(map[string]int, len(catalog.Diagnostics.ResourcesBySource)+1)
	for key, value := range catalog.Diagnostics.ResourcesBySource {
		bySource[key] = value
	}
	seen := make(map[string]bool, len(resources))
	for _, resource := range resources {
		seen[resource.ID] = true
	}

	previousRoots := map[string]*Root{}
	parents := map[string]string{}
	previousNodes := map[string]*Node{}
	var index func(node *Node)
	index = func(node *Node) {
		previousNodes[node.ID] = node
		for _, child := range node.Children {
			parents[child.ID] = node.ID
			index(child)
		}
	}
	for _, root := range options.Previous.Roots {
		previousRoots[root.key()] = root
		if root.Node != nil {
			index(root.Node)
		}
	}
	// Folders that lead to an included item must be listed even when they are
	// excluded themselves.
	wanted := map[string]bool{}
	for id, rule := range options.Selection.Rules {
		if rule != RuleInclude {
			continue
		}
		for parent, ok := parents[id]; ok && !wanted[parent]; parent, ok = parents[parent] {
			wanted[parent] = true
		}
	}

	tree := Tree{ScannedAt: time.Now().UTC().Format(time.RFC3339)}
	done := map[string]bool{}
	for _, item := range links {
		if err := ctx.Err(); err != nil {
			return result, err
		}
		root := &Root{
			ID: item.link.ID, CourseID: item.resource.CourseID, Course: item.resource.CourseName,
			Module: item.resource.ModuleName, LinkName: item.resource.Name, LinkURL: item.resource.URL,
			New: options.Selection.IsNew(item.link.ID),
		}
		if done[root.key()] {
			continue
		}
		done[root.key()] = true
		tree.Roots = append(tree.Roots, root)
		if root.New {
			result.Unreviewed++
		}
		reviewed := !root.New && (options.Selection.Included([]string{root.ID}) || wanted[root.ID])
		previous := previousRoots[root.key()]

		walk := &walker{
			client: client, options: options, wanted: wanted, previous: previousNodes,
			root: root, link: item.resource, visited: map[string]bool{}, seen: seen,
		}
		file, oauth, err := client.Get(ctx, item.link.ID, item.link.ResourceKey)
		if err == nil && file.MimeType == shortcutMIME && file.ShortcutDetails != nil {
			file, err = client.getAs(ctx, file.ShortcutDetails.TargetID, "", oauth)
		}
		if err != nil {
			if ctx.Err() != nil {
				return result, ctx.Err()
			}
			root.Error = err.Error()
			if previous != nil {
				root.Node = previous.Node
			}
			if reviewed {
				walk.fail(err)
				result.Failures = append(result.Failures, walk.failures...)
			}
			continue
		}
		root.OAuth = oauth
		var directory []string
		if file.MimeType == FolderMIME {
			directory = []string{segment(root.LinkName)}
			if options.Full || options.Selection.Included([]string{root.ID}) || wanted[root.ID] {
				progress(options.Progress, fmt.Sprintf("Drive: listando «%s»…", root.LinkName))
			}
		}
		var chain []string
		if file.ID != root.ID {
			chain = []string{root.ID}
		}
		root.Node = walk.node(ctx, file, chain, directory)
		if err := ctx.Err(); err != nil {
			return result, err
		}
		if !root.New {
			result.Failures = append(result.Failures, walk.failures...)
		} else if len(walk.failures) > 0 {
			root.Error = walk.failures[0].Error
		}
		for _, resource := range walk.resources {
			resources = append(resources, resource)
			bySource[Source]++
		}
	}

	sort.SliceStable(resources, func(i, j int) bool {
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
		return a.Name < b.Name
	})
	result.Catalog.Resources = resources
	result.Catalog.Diagnostics.ResourcesBySource = bySource
	result.Catalog.Diagnostics.AccessibleResources += len(resources) - len(catalog.Resources)
	result.Tree = tree
	return result, nil
}

type walker struct {
	client    *Client
	options   ExpandOptions
	wanted    map[string]bool
	previous  map[string]*Node
	root      *Root
	link      moodle.Resource
	visited   map[string]bool
	seen      map[string]bool
	resources []moodle.Resource
	failures  []RootFailure
}

func (w *walker) fail(err error) {
	if len(w.failures) > 0 {
		return // one failure per link is enough to act on
	}
	w.failures = append(w.failures, RootFailure{
		Course: w.root.Course, Module: w.root.Module, Resource: w.root.LinkName,
		Error: "Google Drive: " + err.Error(),
	})
}

// node records file in the tree and, when selected, in the catalog. directory
// is the local folder (below the course section) that holds file's contents
// if it is a folder, or file itself otherwise.
func (w *walker) node(ctx context.Context, file File, chain []string, directory []string) *Node {
	node := &Node{
		ID: file.ID, Name: file.Name, MIME: file.MimeType, Size: file.Size,
		Modified: file.ModifiedTime.Unix(), ResourceKey: file.ResourceKey,
	}
	if file.ModifiedTime.IsZero() {
		node.Modified = 0
	}
	chain = append(chain[:len(chain):len(chain)], file.ID)
	if file.MimeType != FolderMIME {
		node.Kind = KindFile
		if _, exportable := exports[file.MimeType]; !exportable && strings.HasPrefix(file.MimeType, "application/vnd.google-apps.") {
			node.Kind = KindLink
		}
		if w.options.Selection.Included(chain) {
			w.emit(file, node, directory)
		}
		return node
	}

	node.Kind = KindFolder
	if w.visited[file.ID] {
		return node
	}
	w.visited[file.ID] = true
	if !w.options.Full && !w.options.Selection.Included(chain) && !w.wanted[file.ID] {
		if previous := w.previous[file.ID]; previous != nil {
			node.Children = previous.Children
		}
		return node
	}
	children, err := w.client.List(ctx, file.ID, file.ResourceKey, w.root.OAuth)
	if err != nil {
		if ctx.Err() == nil {
			w.fail(err)
		}
		if previous := w.previous[file.ID]; previous != nil {
			node.Children = previous.Children
		}
		return node
	}
	for _, child := range children {
		if ctx.Err() != nil {
			return node
		}
		if child.MimeType == shortcutMIME {
			if child.ShortcutDetails == nil {
				continue
			}
			target, err := w.client.getAs(ctx, child.ShortcutDetails.TargetID, "", w.root.OAuth)
			if err != nil || target.Trashed {
				continue
			}
			child = target
		}
		childDirectory := directory
		if child.MimeType == FolderMIME {
			childDirectory = append(directory[:len(directory):len(directory)], segment(child.Name))
		}
		node.Children = append(node.Children, w.node(ctx, child, chain, childDirectory))
	}
	return node
}

func (w *walker) emit(file File, node *Node, directory []string) {
	id := moodle.StableID(fmt.Sprintf("gdrive|%d|%s", w.root.CourseID, file.ID))
	if w.seen[id] {
		return
	}
	w.seen[id] = true
	resource := moodle.Resource{
		ID: id, CourseID: w.root.CourseID, CourseName: w.root.Course, ModuleName: w.root.Module,
		ActivityName: w.link.ActivityName, CourseModule: w.link.CourseModule,
		Name: file.Name, URL: "https://drive.google.com/file/d/" + file.ID + "/view",
		Subfolder: path.Join(directory...), MIME: file.MimeType, Size: file.Size,
		Modified: node.Modified, Source: Source, Accessible: true,
	}
	ref := &moodle.DriveRef{FileID: file.ID, ResourceKey: file.ResourceKey, UseOAuth: w.root.OAuth}
	switch export, exportable := exports[file.MimeType]; {
	case node.Kind == KindLink:
		resource.Type = moodle.ResourceLink
		resource.Size = 0
		resource.URL = "https://drive.google.com/open?id=" + file.ID
		ref = nil
	case exportable:
		ref.ExportMIME = export.mime
		resource.MIME = export.mime
		resource.Size = 0
		if !strings.EqualFold(path.Ext(resource.Name), export.extension) {
			resource.Name += export.extension
		}
		resource.Type = moodle.ClassifyFile(resource.Name)
	default:
		resource.Type = moodle.ClassifyFile(resource.Name)
	}
	resource.Drive = ref
	w.resources = append(w.resources, resource)
}

// segment keeps a Drive name as one folder level: Drive allows "/" in names.
func segment(name string) string {
	name = strings.NewReplacer("/", "-", "\\", "-").Replace(strings.TrimSpace(name))
	if name == "" {
		return "Drive"
	}
	return name
}

func progress(report moodle.ProgressFunc, message string) {
	if report != nil {
		report(message)
	}
}
