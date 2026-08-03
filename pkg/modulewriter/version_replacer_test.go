/*
Copyright 2026 Google LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
*/

package modulewriter

import (
	"os"
	"path/filepath"
	"testing"
)

func TestValidateAndSanitizeVersion(t *testing.T) {
	tests := []struct {
		name    string
		input   string
		want    string
		wantErr bool
	}{
		{
			name:  "Standard SemVer v-prefixed",
			input: "v1.95.0",
			want:  "v1.95.0",
		},
		{
			name:  "Standard SemVer no prefix",
			input: "1.95.0",
			want:  "v1.95.0",
		},
		{
			name:  "Pre-release SemVer",
			input: "v1.95.0-rc1",
			want:  "v1.95.0-rc1",
		},
		{
			name:  "Dirty developer version",
			input: "v1.95.0-dirty",
			want:  "v1.95.0-dirty",
		},
		{
			name:  "Dirty developer version no prefix",
			input: "1.95.0-dirty",
			want:  "v1.95.0-dirty",
		},
		{
			name:  "Git describe style dirty version",
			input: "v1.95.0-12-g3a4b5c-dirty",
			want:  "v1.95.0-12-g3a4b5c-dirty",
		},
		{
			name:  "Git describe style standard version",
			input: "v1.95.0-12-g3a4b5c",
			want:  "v1.95.0-12-g3a4b5c",
		},
		{
			name:    "Invalid version format",
			input:   "invalid-version",
			wantErr: true,
		},
		{
			name:    "Invalid characters",
			input:   "v1.95.0; injection",
			wantErr: true,
		},
		{
			name:    "Empty version",
			input:   "",
			wantErr: true,
		},
	}

	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			got, err := validateAndSanitizeVersion(tc.input)
			if (err != nil) != tc.wantErr {
				t.Fatalf("validateAndSanitizeVersion(%q) returned error: %v, wantErr: %v", tc.input, err, tc.wantErr)
			}
			if !tc.wantErr && got != tc.want {
				t.Errorf("validateAndSanitizeVersion(%q) = %q, want: %q", tc.input, got, tc.want)
			}
		})
	}
}

func TestReplaceVersionPlaceholders(t *testing.T) {
	tempDir, err := os.MkdirTemp("", "version-replacer-test")
	if err != nil {
		t.Fatalf("failed to create temp dir: %v", err)
	}
	defer os.RemoveAll(tempDir)

	// Create test files
	tfFileContent := `
module "my_module" {
  source = "path/to/module/{{VERSION}}"
  version = "[VERSION]"
}
`
	nonTfFileContent := `
This is a readme with {{VERSION}} and [VERSION].
It should NOT be replaced.
`

	tfFilePath := filepath.Join(tempDir, "main.tf")
	if err := os.WriteFile(tfFilePath, []byte(tfFileContent), 0644); err != nil {
		t.Fatalf("failed to write test tf file: %v", err)
	}

	readmePath := filepath.Join(tempDir, "README.md")
	if err := os.WriteFile(readmePath, []byte(nonTfFileContent), 0644); err != nil {
		t.Fatalf("failed to write test readme file: %v", err)
	}

	version := "1.95.0-dirty"
	if err := ReplaceVersionPlaceholders(tempDir, version); err != nil {
		t.Fatalf("ReplaceVersionPlaceholders failed: %v", err)
	}

	// Verify .tf file replacement
	tfBytes, err := os.ReadFile(tfFilePath)
	if err != nil {
		t.Fatalf("failed to read modified tf file: %v", err)
	}
	gotTfContent := string(tfBytes)
	wantTfContent := `
module "my_module" {
  source = "path/to/module/v1.95.0-dirty"
  version = "v1.95.0-dirty"
}
`
	if gotTfContent != wantTfContent {
		t.Errorf("Modified TF content mismatch.\nGot:\n%s\nWant:\n%s", gotTfContent, wantTfContent)
	}

	// Verify .md file remains unchanged
	readmeBytes, err := os.ReadFile(readmePath)
	if err != nil {
		t.Fatalf("failed to read readme file: %v", err)
	}
	gotReadmeContent := string(readmeBytes)
	if gotReadmeContent != nonTfFileContent {
		t.Errorf("Readme content was modified when it shouldn't have been.\nGot:\n%s\nWant:\n%s", gotReadmeContent, nonTfFileContent)
	}
}
