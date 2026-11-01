package config

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestLegacyGlossaryBecomesLocalWithoutChangingFileOnRead(t *testing.T) {
	dir := t.TempDir()
	raw := []byte(`{"enabled":true,"entries":[{"source":"dancer roll","target":"浮辊","context":"张力控制","source_lang":"en","target_lang":"zh","enabled":true}]}`)
	path := filepath.Join(dir, "glossary.json")
	if err := os.WriteFile(path, raw, 0600); err != nil {
		t.Fatal(err)
	}
	value, err := LoadGlossary(dir)
	if err != nil || len(value.Entries) != 1 || value.Entries[0].Target != "浮辊" || (value.LocalEnabled != nil && !*value.LocalEnabled) {
		t.Fatalf("legacy data lost: %+v %v", value, err)
	}
	after, _ := os.ReadFile(path)
	if string(after) != string(raw) {
		t.Fatal("read modified old data")
	}
	value.Libraries = []GlossaryLibrary{{ID: "film", Name: "薄膜收放卷", Enabled: true, Entries: []GlossaryEntry{value.Entries[0]}}}
	if err := SaveGlossary(dir, value); err != nil {
		t.Fatal(err)
	}
	value, _ = LoadGlossary(dir)
	if len(value.Entries) != 1 || len(value.Libraries) != 1 || !value.Libraries[0].Enabled {
		t.Fatal("local or named library not preserved")
	}
	value.Libraries[0].Enabled = false
	if err := SaveGlossary(dir, value); err != nil {
		t.Fatal(err)
	}
	value, _ = LoadGlossary(dir)
	if value.Libraries[0].Enabled || len(value.Libraries[0].Entries) != 1 {
		t.Fatal("disabling deleted library contents")
	}
}

func TestGlossaryLibraryIdentityValidation(t *testing.T) {
	for _, libraries := range [][]GlossaryLibrary{
		{{ID: "local", Name: "另一个库"}},
		{{ID: "a", Name: "本地术语库"}},
		{{ID: "a", Name: "Film"}, {ID: "b", Name: "film"}},
		{{ID: "a", Name: "Film"}, {ID: "a", Name: "Paper"}},
		{{ID: "../path", Name: "Film"}},
	} {
		value := DefaultGlossary()
		value.Libraries = libraries
		if err := SaveGlossary(t.TempDir(), value); err == nil {
			t.Fatalf("invalid libraries accepted: %+v", libraries)
		}
	}
}

func TestGlossaryRejectsContentThatCannotBeReloaded(t *testing.T) {
	dir := t.TempDir()
	glossary := DefaultGlossary()
	entry := GlossaryEntry{Source: strings.Repeat("词", 80), Target: strings.Repeat("译", 80), Context: strings.Repeat("义", 160), SourceLang: "en", TargetLang: "zh", Enabled: true}
	glossary.Entries = make([]GlossaryEntry, 3000)
	for i := range glossary.Entries {
		glossary.Entries[i] = entry
	}
	if err := SaveGlossary(dir, glossary); err == nil {
		t.Fatal("expected file size limit before writing")
	}
	loaded, err := LoadGlossary(dir)
	if err != nil || loaded.Revision != "missing" {
		t.Fatal("oversized save replaced existing state")
	}
}

func TestGlossarySaveReloadAndReplace(t *testing.T) {
	dir := t.TempDir()
	glossary, err := LoadGlossary(dir)
	if err != nil || glossary.Enabled || len(glossary.Entries) != 3 {
		t.Fatal("expected disabled editable examples")
	}
	glossary.Enabled = true
	if err = SaveGlossary(dir, glossary); err != nil {
		t.Fatal(err)
	}
	glossary, _ = LoadGlossary(dir)
	glossary.Entries[0].Target = "连续膜材"
	if err = SaveGlossary(dir, glossary); err != nil {
		t.Fatal(err)
	}
	loaded, err := LoadGlossary(dir)
	if err != nil || !loaded.Enabled || loaded.Entries[0].Target != "连续膜材" {
		t.Fatal("save did not replace existing glossary")
	}
	glossary.Entries[0].Source = ""
	if err = SaveGlossary(dir, glossary); err == nil {
		t.Fatal("empty term accepted")
	}
	loaded, _ = LoadGlossary(dir)
	if loaded.Entries[0].Target != "连续膜材" {
		t.Fatal("invalid edit replaced existing data")
	}
}

func TestGlossaryRejectsStaleEditorWithoutOverwriting(t *testing.T) {
	dir := t.TempDir()
	old, _ := LoadGlossary(dir)
	if err := SaveGlossary(dir, old); err != nil {
		t.Fatal(err)
	}
	current, _ := LoadGlossary(dir)
	current.Enabled = true
	if err := SaveGlossary(dir, current); err != nil {
		t.Fatal(err)
	}
	if err := SaveGlossary(dir, old); err == nil {
		t.Fatal("stale editor overwrote newer data")
	}
	saved, _ := LoadGlossary(dir)
	if !saved.Enabled {
		t.Fatal("saved content changed")
	}
}
