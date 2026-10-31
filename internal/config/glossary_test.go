package config

import "testing"

func TestGlossarySaveReloadAndReplace(t *testing.T) {
	dir := t.TempDir()
	glossary, err := LoadGlossary(dir)
	if err != nil || glossary.Enabled || len(glossary.Entries) != 2 {
		t.Fatal("expected disabled editable examples")
	}
	glossary.Enabled = true
	if err = SaveGlossary(dir, glossary); err != nil {
		t.Fatal(err)
	}
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
