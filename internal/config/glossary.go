package config

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"unicode/utf8"
)

type GlossaryEntry struct {
	Source     string `json:"source"`
	Target     string `json:"target"`
	Context    string `json:"context"`
	SourceLang string `json:"source_lang"`
	TargetLang string `json:"target_lang"`
	Enabled    bool   `json:"enabled"`
}

type Glossary struct {
	Enabled bool            `json:"enabled"`
	Domain  string          `json:"domain"`
	Entries []GlossaryEntry `json:"entries"`
}

func DefaultGlossary() Glossary {
	return Glossary{Domain: "西门子／卷绕", Entries: []GlossaryEntry{
		{Source: "web", Target: "膜材／连续料带", Context: "薄膜、纸张等连续材料的输送与张力控制；网页、网络语境采用其他含义", SourceLang: "en", TargetLang: "zh", Enabled: true},
		{Source: "winder", Target: "卷绕装置／收卷机", Context: "连续材料收卷设备；结合句意选择卷绕、收卷机等表达", SourceLang: "en", TargetLang: "zh", Enabled: true},
	}}
}

func LoadGlossary(baseDir string) (Glossary, error) {
	data, err := os.ReadFile(filepath.Join(baseDir, "glossary.json"))
	if errors.Is(err, os.ErrNotExist) {
		return DefaultGlossary(), nil
	}
	if err != nil {
		return Glossary{}, err
	}
	if len(data) > 2_000_000 {
		return Glossary{}, errors.New("术语表文件过大")
	}
	var glossary Glossary
	if err := json.Unmarshal(data, &glossary); err != nil {
		return Glossary{}, errors.New("术语表文件格式错误")
	}
	if glossary.Entries == nil {
		glossary.Entries = []GlossaryEntry{}
	}
	return glossary, nil
}

func SaveGlossary(baseDir string, glossary Glossary) error {
	if glossary.Entries == nil {
		glossary.Entries = []GlossaryEntry{}
	}
	if len(glossary.Entries) > 3000 || utf8.RuneCountInString(glossary.Domain) > 80 {
		return errors.New("术语表最多 3000 条，领域说明最多 80 字")
	}
	for i := range glossary.Entries {
		row := &glossary.Entries[i]
		row.Source = strings.TrimSpace(row.Source)
		row.Target = strings.TrimSpace(row.Target)
		if row.Source == "" || row.Target == "" || utf8.RuneCountInString(row.Source) > 80 || utf8.RuneCountInString(row.Target) > 80 || utf8.RuneCountInString(row.Context) > 160 {
			return errors.New("原词和参考译法必填且不超过 80 字，适用语境最多 160 字")
		}
		if !((row.SourceLang == "en" && row.TargetLang == "zh") || (row.SourceLang == "zh" && row.TargetLang == "en")) {
			return errors.New("当前术语表支持英译中和中译英")
		}
	}
	data, err := json.MarshalIndent(glossary, "", "  ")
	if err != nil {
		return err
	}
	tmp, err := os.CreateTemp(baseDir, ".glossary-*.tmp")
	if err != nil {
		return err
	}
	name := tmp.Name()
	defer os.Remove(name)
	if _, err = tmp.Write(data); err != nil {
		tmp.Close()
		return err
	}
	if err = tmp.Close(); err != nil {
		return err
	}
	return os.Rename(name, filepath.Join(baseDir, "glossary.json"))
}
