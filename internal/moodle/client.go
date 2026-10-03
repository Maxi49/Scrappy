package moodle

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

const maxAPIResponse = 64 << 20

type Client struct {
	baseURL        *url.URL
	token          string
	httpClient     *http.Client
	downloadClient *http.Client
	retry          RetryConfig
}

func NewClient(baseURL, token string) (*Client, error) {
	parsed, err := url.Parse(strings.TrimRight(baseURL, "/"))
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return nil, fmt.Errorf("URL de Moodle inválida")
	}
	if parsed.Scheme != "https" && parsed.Scheme != "http" {
		return nil, fmt.Errorf("Moodle debe usar HTTP o HTTPS")
	}
	return &Client{
		baseURL: parsed,
		token:   token,
		httpClient: &http.Client{
			Timeout: 2 * time.Minute,
		},
		// File transfers need more time on slow connections, especially when
		// several downloads share the available bandwidth. API calls keep
		// their shorter timeout; cancellation still uses the request context.
		downloadClient: &http.Client{
			Timeout: 15 * time.Minute,
		},
		retry: RetryConfig{Attempts: 3, BaseWait: 250 * time.Millisecond},
	}, nil
}

func (c *Client) Token() string { return c.token }

func (c *Client) Authenticate(ctx context.Context, username, password string) error {
	if strings.TrimSpace(username) == "" || password == "" {
		return errors.New("faltan usuario o contraseña")
	}
	values := url.Values{
		"username": {username},
		"password": {password},
		"service":  {"moodle_mobile_app"},
	}
	body, err := c.postForm(ctx, "/login/token.php", values)
	if err != nil {
		return fmt.Errorf("autenticación: %w", err)
	}
	var response struct {
		Token     string `json:"token"`
		Error     string `json:"error"`
		ErrorCode string `json:"errorcode"`
	}
	if err := json.Unmarshal(body, &response); err != nil {
		return errors.New("Moodle devolvió una respuesta de autenticación inválida")
	}
	if response.Token == "" {
		message := response.Error
		if message == "" {
			message = response.ErrorCode
		}
		if message == "" {
			message = "credenciales rechazadas o servicio móvil deshabilitado"
		}
		return errors.New(message)
	}
	c.token = response.Token
	return nil
}

func (c *Client) Call(ctx context.Context, function string, params url.Values, target any) error {
	if c.token == "" {
		return errors.New("no hay token de Moodle")
	}
	if params == nil {
		params = make(url.Values)
	}
	params.Set("wstoken", c.token)
	params.Set("wsfunction", function)
	params.Set("moodlewsrestformat", "json")
	body, err := c.postForm(ctx, "/webservice/rest/server.php", params)
	if err != nil {
		return fmt.Errorf("%s: %w", function, err)
	}
	var apiErr APIException
	if json.Unmarshal(body, &apiErr) == nil && apiErr.Exception != "" {
		message := strings.TrimSpace(apiErr.Message)
		if message == "" {
			message = apiErr.ErrorCode
		}
		if message == "" {
			message = apiErr.Exception
		}
		return fmt.Errorf("%s: %s", function, message)
	}
	if err := json.Unmarshal(body, target); err != nil {
		return fmt.Errorf("%s devolvió JSON inválido: %w", function, err)
	}
	return nil
}

func (c *Client) CallRaw(ctx context.Context, function string, params url.Values) (any, error) {
	var result any
	if err := c.Call(ctx, function, params, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *Client) SiteInfo(ctx context.Context) (SiteInfo, error) {
	var info SiteInfo
	err := c.Call(ctx, "core_webservice_get_site_info", nil, &info)
	return info, err
}

func (c *Client) EnrolledCourses(ctx context.Context, userID int) ([]Course, error) {
	params := url.Values{"userid": {strconv.Itoa(userID)}}
	var raw []rawCourse
	if err := c.Call(ctx, "core_enrol_get_users_courses", params, &raw); err != nil {
		return nil, err
	}
	courses := make([]Course, 0, len(raw))
	for _, item := range raw {
		name := strings.TrimSpace(item.FullName)
		if item.ID == 0 || name == "" {
			continue
		}
		courseURL := item.ViewURL
		if courseURL == "" {
			courseURL = c.baseURL.ResolveReference(&url.URL{Path: "/course/view.php", RawQuery: "id=" + strconv.Itoa(item.ID)}).String()
		}
		courses = append(courses, Course{ID: item.ID, Name: name, URL: courseURL})
	}
	return courses, nil
}

func (c *Client) CourseContents(ctx context.Context, courseID int) ([]courseSection, error) {
	params := url.Values{"courseid": {strconv.Itoa(courseID)}}
	var sections []courseSection
	err := c.Call(ctx, "core_course_get_contents", params, &sections)
	return sections, err
}

func CourseIDsParams(courses []Course) url.Values {
	values := make(url.Values)
	for index, course := range courses {
		values.Set(fmt.Sprintf("courseids[%d]", index), strconv.Itoa(course.ID))
	}
	return values
}

func (c *Client) DownloadURL(raw string) (string, error) {
	parsed, err := url.Parse(raw)
	if err != nil {
		return "", errors.New("URL de archivo inválida")
	}
	if !strings.EqualFold(parsed.Host, c.baseURL.Host) {
		return raw, nil
	}
	// Links pasted into HTML point at the browser endpoint, which needs a
	// session cookie. The Web Services twin serves the same file to a token.
	if !strings.Contains(parsed.Path, "/webservice/pluginfile.php/") {
		parsed.Path = strings.Replace(parsed.Path, "/pluginfile.php/", "/webservice/pluginfile.php/", 1)
		parsed.RawPath = strings.Replace(parsed.RawPath, "/pluginfile.php/", "/webservice/pluginfile.php/", 1)
	}
	path := strings.ToLower(parsed.Path)
	if strings.Contains(path, "/webservice/pluginfile.php") || strings.Contains(path, "/tokenpluginfile.php") {
		query := parsed.Query()
		query.Set("token", c.token)
		parsed.RawQuery = query.Encode()
	}
	return parsed.String(), nil
}

// HTTPClient returns the client for file downloads.
func (c *Client) HTTPClient() *http.Client { return c.downloadClient }

func (c *Client) postForm(ctx context.Context, endpoint string, values url.Values) ([]byte, error) {
	target := c.baseURL.ResolveReference(&url.URL{Path: endpoint}).String()
	attempts := c.retry.Attempts
	if attempts < 1 {
		attempts = 1
	}
	var lastErr error
	for attempt := 0; attempt < attempts; attempt++ {
		request, err := http.NewRequestWithContext(ctx, http.MethodPost, target, bytes.NewBufferString(values.Encode()))
		if err != nil {
			return nil, err
		}
		request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
		request.Header.Set("Accept", "application/json")
		request.Header.Set("User-Agent", "Scrappy/2 Go")
		response, err := c.httpClient.Do(request)
		if err == nil {
			body, readErr := io.ReadAll(io.LimitReader(response.Body, maxAPIResponse+1))
			response.Body.Close()
			if readErr != nil {
				lastErr = readErr
			} else if len(body) > maxAPIResponse {
				return nil, errors.New("respuesta de Moodle demasiado grande")
			} else if response.StatusCode >= 200 && response.StatusCode < 300 {
				return body, nil
			} else {
				lastErr = fmt.Errorf("HTTP %d", response.StatusCode)
				if response.StatusCode != http.StatusTooManyRequests && response.StatusCode < 500 {
					return nil, lastErr
				}
			}
		} else {
			lastErr = err
		}
		if attempt+1 < attempts {
			wait := c.retry.BaseWait * time.Duration(1<<attempt)
			select {
			case <-ctx.Done():
				return nil, ctx.Err()
			case <-time.After(wait):
			}
		}
	}
	return nil, lastErr
}
