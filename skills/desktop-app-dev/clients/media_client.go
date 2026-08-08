package media

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
)

type MediaClient struct {
	BaseURL string
	HTTP    *http.Client
	Token   string
}

func NewMediaClient(baseURL string, token ...string) *MediaClient {
	client := &MediaClient{BaseURL: baseURL, HTTP: http.DefaultClient}
	if len(token) > 0 {
		client.Token = token[0]
	}
	return client
}

func (c *MediaClient) Enqueue(kind string, payload any, dedupeKey string, priority int) (map[string]any, error) {
	body, _ := json.Marshal(map[string]any{
		"kind": kind, "payload": payload, "dedupe_key": dedupeKey, "priority": priority,
	})
	req, err := http.NewRequest("POST", c.BaseURL+"/tasks", bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	c.auth(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	var result map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *MediaClient) Task(id int64) (map[string]any, error) {
	req, err := http.NewRequest("GET", fmt.Sprintf("%s/tasks/%d", c.BaseURL, id), nil)
	if err != nil {
		return nil, err
	}
	c.auth(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *MediaClient) DepsProgress() (map[string]any, error) {
	req, err := http.NewRequest("GET", c.BaseURL+"/deps/progress", nil)
	if err != nil {
		return nil, err
	}
	c.auth(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *MediaClient) DepsStatus() (map[string]any, error) {
	req, err := http.NewRequest("GET", c.BaseURL+"/deps/status", nil)
	if err != nil {
		return nil, err
	}
	c.auth(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *MediaClient) InstallDeps() (map[string]any, error) {
	req, err := http.NewRequest("POST", c.BaseURL+"/deps/install", nil)
	if err != nil {
		return nil, err
	}
	c.auth(req)
	resp, err := c.HTTP.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	var result map[string]any
	if err := json.Unmarshal(data, &result); err != nil {
		return nil, err
	}
	return result, nil
}

func (c *MediaClient) auth(req *http.Request) {
	if c.Token != "" {
		req.Header.Set("Authorization", "Bearer "+c.Token)
	}
}
