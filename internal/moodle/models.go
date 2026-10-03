package moodle

import "time"

// Course is the small, stable course representation shared with the Python UI.
type Course struct {
	ID   int    `json:"id"`
	Name string `json:"name"`
	URL  string `json:"url"`
}

type ResourceType string

const (
	ResourceFile       ResourceType = "file"
	ResourcePDF        ResourceType = "pdf"
	ResourcePowerPoint ResourceType = "powerpoint"
	ResourceWord       ResourceType = "word"
	ResourceLink       ResourceType = "link"
	ResourceGoogle     ResourceType = "google_drive"
	ResourceYouTube    ResourceType = "youtube"
)

// Resource is a downloadable Moodle file or a link worth preserving locally.
// ModuleName intentionally means the course section/tile to preserve Scrappy's
// existing output layout. ActivityName identifies the activity inside it.
type Resource struct {
	ID           string       `json:"id"`
	CourseID     int          `json:"course_id"`
	CourseName   string       `json:"materia"`
	ModuleName   string       `json:"modulo"`
	ActivityName string       `json:"actividad,omitempty"`
	CourseModule int          `json:"course_module,omitempty"`
	Name         string       `json:"nombre"`
	URL          string       `json:"url"`
	Type         ResourceType `json:"tipo"`
	Subfolder    string       `json:"subcarpeta,omitempty"`
	MIME         string       `json:"mimetype,omitempty"`
	Size         int64        `json:"filesize,omitempty"`
	Modified     int64        `json:"timemodified,omitempty"`
	Source       string       `json:"fuente"`
	Accessible   bool         `json:"accesible"`

	// Drive is set on files listed from a Google Drive link; they download
	// through the Drive fetcher instead of Moodle.
	Drive *DriveRef `json:"-"`

	// embedded marks a file found only as a link inside HTML. The activity
	// that actually owns the file wins when both describe the same file.
	embedded bool
}

// DriveRef tells the Drive fetcher how to download one file.
type DriveRef struct {
	FileID      string
	ResourceKey string
	ExportMIME  string // empty for regular files
	UseOAuth    bool
}

func (r Resource) IsLink() bool {
	return r.Type == ResourceLink || r.Type == ResourceGoogle || r.Type == ResourceYouTube
}

type Diagnostics struct {
	Sections                       int            `json:"sections"`
	Activities                     int            `json:"activities"`
	InaccessibleModules            int            `json:"inaccessible_modules"`
	AccessibleResources            int            `json:"accessible_resources"`
	InaccessibleResources          int            `json:"inaccessible_resources"`
	ContentItemsByType             map[string]int `json:"content_items_by_type"`
	ResourcesBySource              map[string]int `json:"resources_by_source"`
	DuplicateResources             int            `json:"duplicate_resources"`
	ActivitiesWithoutDirectContent map[string]int `json:"activities_without_direct_content"`
	CourseErrors                   []CourseError  `json:"course_errors,omitempty"`
	Warnings                       []string       `json:"warnings,omitempty"`
}

// CourseError records a course whose contents could not be analysed. The rest
// of the selection is still synchronised; the error surfaces in the report.
type CourseError struct {
	Course string `json:"materia"`
	Error  string `json:"error"`
}

type Catalog struct {
	Resources   []Resource  `json:"resources"`
	Diagnostics Diagnostics `json:"diagnostics"`
}

type SiteInfo struct {
	UserID    int `json:"userid"`
	Functions []struct {
		Name string `json:"name"`
	} `json:"functions"`
}

type rawCourse struct {
	ID       int    `json:"id"`
	FullName string `json:"fullname"`
	ViewURL  string `json:"viewurl"`
}

type courseSection struct {
	ID      int            `json:"id"`
	Name    string         `json:"name"`
	Section int            `json:"section"`
	Modules []courseModule `json:"modules"`
}

type courseModule struct {
	ID           int           `json:"id"`
	Name         string        `json:"name"`
	ModName      string        `json:"modname"`
	URL          string        `json:"url"`
	Description  string        `json:"description"`
	Visible      any           `json:"visible"`
	UserVisible  any           `json:"uservisible"`
	Contents     []contentItem `json:"contents"`
	Downloadable int           `json:"downloadcontent"`
}

type contentItem struct {
	Type           string `json:"type"`
	Filename       string `json:"filename"`
	Filepath       string `json:"filepath"`
	Filesize       int64  `json:"filesize"`
	FileURL        string `json:"fileurl"`
	MIME           string `json:"mimetype"`
	TimeModified   int64  `json:"timemodified"`
	IsExternalFile bool   `json:"isexternalfile"`

	embedded bool
}

type APIException struct {
	Exception string `json:"exception"`
	ErrorCode string `json:"errorcode"`
	Message   string `json:"message"`
}

type RetryConfig struct {
	Attempts int
	BaseWait time.Duration
}
