package config

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
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
	Revision     string            `json:"revision,omitempty"`
	Enabled      bool              `json:"enabled"`
	Domain       string            `json:"domain"`
	Entries      []GlossaryEntry   `json:"entries"`
	LocalEnabled *bool             `json:"local_enabled,omitempty"`
	Libraries    []GlossaryLibrary `json:"libraries,omitempty"`
}

type GlossaryLibrary struct {
	ID      string          `json:"id"`
	Name    string          `json:"name"`
	Enabled bool            `json:"enabled"`
	Entries []GlossaryEntry `json:"entries"`
}

func DefaultGlossary() Glossary {
	return Glossary{Revision: "missing", Entries: []GlossaryEntry{
		{Source: "web", Target: "膜材／连续料带", Context: "薄膜、纸张等连续材料的输送与张力控制；网页、网络语境采用其他含义", SourceLang: "en", TargetLang: "zh", Enabled: true},
		{Source: "web", Target: "网页／网络", Context: "浏览器、互联网、网页应用", SourceLang: "en", TargetLang: "zh", Enabled: true},
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
	glossary.Revision = fmt.Sprintf("%x", sha256.Sum256(data))
	return glossary, nil
}

func SaveGlossary(baseDir string, glossary Glossary) error {
	if glossary.Revision != "" {
		current, err := LoadGlossary(baseDir)
		if err != nil {
			return err
		}
		if current.Revision != glossary.Revision {
			return errors.New("术语库已被其他窗口或程序修改，请先重新载入，避免覆盖新内容")
		}
	}
	if glossary.Entries == nil {
		glossary.Entries = []GlossaryEntry{}
	}
	if len(glossary.Libraries) > 32 {
		return errors.New("最多创建 32 个附加术语库")
	}
	if len(glossary.Entries) > 3000 || utf8.RuneCountInString(glossary.Domain) > 80 {
		return errors.New("术语表最多 3000 条，领域说明最多 80 字")
	}
	sets := [][]GlossaryEntry{glossary.Entries}
	ids, names := map[string]bool{"local": true}, map[string]bool{"本地术语库": true}
	total := len(glossary.Entries)
	for i := range glossary.Libraries {
		library := &glossary.Libraries[i]
		library.Name = strings.TrimSpace(library.Name)
		nameKey := strings.ToLower(library.Name)
		if !regexp.MustCompile(`^[a-zA-Z0-9_-]{1,64}$`).MatchString(library.ID) || ids[library.ID] || library.Name == "" || utf8.RuneCountInString(library.Name) > 40 || names[nameKey] {
			return errors.New("术语库名称需唯一且不超过 40 字，标识不可重复")
		}
		if len(library.Entries) > 3000 {
			return errors.New("每个术语库最多 3000 条")
		}
		ids[library.ID], names[nameKey] = true, true
		if library.Entries == nil {
			library.Entries = []GlossaryEntry{}
		}
		total += len(library.Entries)
		sets = append(sets, library.Entries)
	}
	if total > 12000 {
		return errors.New("全部术语库合计最多 12000 条")
	}
	for _, entries := range sets {
		for i := range entries {
			row := &entries[i]
			row.Source = strings.TrimSpace(row.Source)
			row.Target = strings.TrimSpace(row.Target)
			if row.Source == "" || row.Target == "" || utf8.RuneCountInString(row.Source) > 80 || utf8.RuneCountInString(row.Target) > 80 || utf8.RuneCountInString(row.Context) > 160 {
				return errors.New("原词和参考译法必填且不超过 80 字，适用语境最多 160 字")
			}
			if !((row.SourceLang == "en" && row.TargetLang == "zh") || (row.SourceLang == "zh" && row.TargetLang == "en")) {
				return errors.New("当前术语表支持英译中和中译英")
			}
		}
	}
	glossary.Revision = ""
	data, err := json.MarshalIndent(glossary, "", "  ")
	if err != nil {
		return err
	}
	if len(data) > 2_000_000 {
		return errors.New("术语库内容超过 2 MB，请减少条目或缩短含义说明")
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
