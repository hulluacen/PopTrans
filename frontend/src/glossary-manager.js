import "./glossary-manager.css"

const escape = value => String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"})[ch])
const keys = ["source", "target", "context"]
const labels = ["原词", "参考译法", "适用语境（可选）"]
const clone = value => JSON.parse(JSON.stringify(value))
const termKey = row => [row.source.trim().toLowerCase(), row.target.trim(), row.context.trim(), row.source_lang, row.target_lang].join("\u0000")

export function parseTermTable(text, delimiter = "\t") {
  const rows = []; let row = [], cell = "", quoted = false
  text = text.replace(/^\uFEFF/, "")
  for (let i = 0; i < text.length; i++) {
    const ch = text[i]
    if (ch === '"' && (quoted || !cell)) {
      if (quoted && text[i + 1] === '"') { cell += '"'; i++ }
      else quoted = !quoted
    } else if (!quoted && ch === delimiter) { row.push(cell); cell = "" }
    else if (!quoted && (ch === "\n" || ch === "\r")) {
      if (ch === "\r" && text[i + 1] === "\n") i++
      row.push(cell); rows.push(row); row = []; cell = ""
    } else cell += ch
  }
  if (quoted) throw new Error("引号未闭合，请检查粘贴或导入的内容")
  if (cell || row.length) { row.push(cell); rows.push(row) }
  return rows.filter(row => row.some(cell => cell.trim()))
}

export function mountGlossaryManager(root, api) {
  let data = {enabled:false, domain:"", entries:[]}, saved = "", loaded = false, saving = false
  let activeLibrary = "local", librarySignature = ""
  let direction = "en-zh", query = "", selected = new Set(), history = [], future = [], historyBytes = 0
  let activeBefore = null, dirty = false, pending = null, page = 0
  const library = () => {
    if(activeLibrary!=="local") { const found=(data.libraries||[]).find(item=>item.id===activeLibrary);if(found)return found;activeLibrary="local" }
    return {id:"local",name:"本地术语库",enabled:data.local_enabled!==false,entries:data.entries}
  }
  const entries = () => library().entries
  const setEntries = rows => { if(activeLibrary==="local")data.entries=rows;else library().entries=rows }
  const normalize = value => {
    const rows = list => (list||[]).map(row=>({...row,source:String(row.source||""),target:String(row.target||""),context:String(row.context||""),enabled:row.enabled!==false}))
    return {enabled:Boolean(value.enabled),domain:value.domain||"",revision:value.revision||"",local_enabled:value.local_enabled!==false,entries:rows(value.entries),libraries:(value.libraries||[]).map(item=>({id:String(item.id),name:String(item.name),enabled:Boolean(item.enabled),entries:rows(item.entries)}))}
  }
  const fingerprint = () => JSON.stringify({...data, revision:undefined})
  const newEntry = () => { const [source_lang,target_lang] = direction.split("-"); return {source:"",target:"",context:"",source_lang,target_lang,enabled:true} }
  const visible = () => entries().map((row,index)=>({row,index})).filter(({row}) => `${row.source_lang}-${row.target_lang}` === direction && (!query || keys.some(key=>row[key].toLowerCase().includes(query))))
  const empty = row => !row.source.trim() && !row.target.trim() && !row.context.trim()
  const node = id => root.querySelector(`#${id}`)

  root.innerHTML = `<main class="glossary-manager">
    <header class="gm-header"><div><h1>术语库</h1><p>同词可有多个含义，翻译时按语境参考</p></div><button id="gmClose" class="gm-icon" aria-label="关闭术语库">×</button></header>
    <div class="gm-body"><aside class="gm-sidebar"><div class="gm-library-heading"><strong>词库列表</strong><button id="gmNewLibrary">新建</button></div><div id="gmLibraries"></div><p class="gm-library-help">勾选需要启用的词库，保存后生效。同词条以本地库优先，同库多义保留。</p></aside><section class="gm-editor">
    <div class="gm-library-title"><strong id="gmLibraryName">本地术语库</strong><button id="gmRenameLibrary">重命名</button><button id="gmRemoveLibrary">删除词库</button></div>
    <div class="gm-toolbar">
      <input id="gmSearch" type="search" placeholder="搜索原词、译法或含义" aria-label="搜索术语" />
      <select id="gmDirection" aria-label="语言方向"><option value="en-zh">英 → 中</option><option value="zh-en">中 → 英</option></select>
      <label class="gm-enable"><input id="gmEnabled" type="checkbox" /> 术语总开关</label>
    </div>
    <div class="gm-actions">
      <button id="gmAdd">新增</button><button id="gmPaste">批量粘贴</button><button id="gmImport" title="追加到当前选中的词库">导入 CSV / TSV</button><button id="gmExport" title="仅导出当前选中的词库">导出当前库</button>
      <button id="gmDelete" disabled>删除已选</button><span class="gm-spacer"></span><button id="gmUndo" disabled title="Ctrl+Z">撤销</button><button id="gmRedo" disabled title="Ctrl+Shift+Z">重做</button>
    </div>
    <div class="gm-table-wrap" id="gmTableWrap"><table class="gm-table"><colgroup><col class="gm-select-col"/><col class="gm-number-col"/><col/><col/><col class="gm-context-col"/></colgroup>
      <thead><tr><th><input id="gmSelectAll" type="checkbox" aria-label="选择当前列表" /></th><th>#</th>${labels.map(label=>`<th>${label}</th>`).join("")}</tr></thead><tbody id="gmBody"></tbody></table></div>
    <div class="gm-hint">Tab 切换单元格，Enter 向下继续；可直接粘贴 Excel 的两列或三列。同一原词的不同含义分别占一行。</div>
    <footer class="gm-footer"><div><span id="gmCount"></span><span id="gmStatus" role="status" aria-live="polite"></span></div><button id="gmPrev" aria-label="上一页">‹</button><span id="gmPage"></span><button id="gmNext" aria-label="下一页">›</button><button id="gmReload">重新载入</button><button id="gmSave" class="gm-primary" disabled>保存词库</button></footer>
    </section></div>
    <input id="gmFile" type="file" accept=".csv,.tsv,.txt" hidden/><div id="gmModal" class="gm-modal" hidden></div>
  </main>`

  function status(message, error = false) { node("gmStatus").textContent = message; node("gmStatus").classList.toggle("gm-error",error) }
  function switchLibrary(id) {
    flush();activeLibrary=id;query="";node("gmSearch").value="";selected.clear();page=0;table();chrome()
  }
  function renderLibraries() {
    const current=library()
    node("gmLibraryName").textContent=current.name
    node("gmRenameLibrary").disabled=!loaded||saving||activeLibrary==="local"
    node("gmRemoveLibrary").disabled=!loaded||saving||activeLibrary==="local"
    const all=[{id:"local",name:"本地术语库",enabled:data.local_enabled!==false,entries:data.entries},...(data.libraries||[])]
    const signature=JSON.stringify([activeLibrary,...all.map(item=>[item.id,item.name,item.enabled,item.entries.filter(row=>!empty(row)).length])])
    if(signature===librarySignature)return
    librarySignature=signature
    node("gmLibraries").innerHTML=all.map(item=>`<div class="gm-library-row ${item.id===activeLibrary?'gm-library-selected':''}"><input type="checkbox" data-library-enabled="${escape(item.id)}" aria-label="启用${escape(item.name)}" ${item.enabled?'checked':''}/><button type="button" data-library-id="${escape(item.id)}" title="${escape(item.name)}"><span>${escape(item.name)}</span><small>${item.entries.filter(row=>!empty(row)).length} 条${item.id==='local'?' · 固定':''}</small></button></div>`).join("")
    node("gmLibraries").querySelectorAll("[data-library-id]").forEach(button=>button.addEventListener("click",()=>switchLibrary(button.dataset.libraryId)))
    node("gmLibraries").querySelectorAll("[data-library-enabled]").forEach(input=>input.addEventListener("change",()=>{
      const id=input.dataset.libraryEnabled,checked=input.checked
      change(()=>{if(id==="local")data.local_enabled=checked;else data.libraries.find(item=>item.id===id).enabled=checked})
    }))
  }
  function chrome() {
    root.querySelectorAll(".gm-toolbar,.gm-actions,.gm-table-wrap,.gm-sidebar,.gm-library-title").forEach(element=>{element.inert=!loaded||saving})
    node("gmReload").disabled=saving
    renderLibraries()
    node("gmCount").textContent = `${visible().length} / ${entries().filter(row=>!empty(row)).length} 条`
    node("gmSave").disabled = !loaded || saving || !dirty
    node("gmSave").textContent = saving ? "保存中…" : "保存词库"
    node("gmUndo").disabled = !history.length; node("gmRedo").disabled = !future.length
    node("gmDelete").disabled = !selected.size
    node("gmDelete").textContent = selected.size ? `删除已选 ${selected.size} 条` : "删除已选"
    node("gmEnabled").checked = data.enabled
    if (loaded && !saving) status(dirty ? "有未保存修改" : "已保存 · 下次翻译使用此版本")
  }
  function remember(before) {
    const after = JSON.stringify(data)
    if (before !== after) {
      history.push({before,after}); historyBytes += before.length + after.length; future = []
      while (history.length > 30 || (historyBytes > 4_000_000 && history.length > 1)) { const old=history.shift();historyBytes-=old.before.length+old.after.length }
    }
    dirty = fingerprint() !== saved; chrome()
  }
  function flush() { if (activeBefore !== null) { const before=activeBefore; activeBefore=null; remember(before) } }
  function change(fn) { flush();const before=JSON.stringify(data);fn();remember(before);table() }
  function undo(redo = false) {
    flush();const from=redo?future:history, to=redo?history:future, item=from.pop();if(!item)return
    data=JSON.parse(redo?item.after:item.before);to.push(item)
    historyBytes=history.reduce((sum,item)=>sum+item.before.length+item.after.length,0)
    selected.clear();dirty=fingerprint()!==saved;table();chrome()
  }
  function focusCell(index,col) {
    const order=visible().map(item=>item.index);order.push(entries().length)
    page=Math.floor(Math.max(0,order.indexOf(index))/200);table()
    const input=root.querySelector(`input[data-row="${index}"][data-col="${col}"]`);input?.focus();input?.select()
  }
  function table() {
    const all=visible();page=Math.max(0,Math.min(page,Math.floor(all.length/200)))
    const items=all.slice(page*200,page*200+200); const virtual=entries().length
    const rowHTML = (row,index,isBlank=false) => `<tr class="${isBlank?'gm-blank':''} ${row.enabled===false?'gm-inactive':''}">
      <td><input data-select="${index}" type="checkbox" aria-label="选择第 ${index+1} 条" ${selected.has(index)?"checked":""} ${isBlank?"disabled":""}/></td>
      <td class="gm-row-number" title="${row.enabled===false?'旧版已停用条目':''}">${isBlank?"+":index+1}${row.enabled===false?`<button class="gm-restore" data-restore="${index}" title="重新启用此条目">启用</button>`:""}</td>
      ${keys.map((key,col)=>`<td><input data-row="${index}" data-col="${col}" value="${escape(row[key])}" maxlength="${col===2?160:80}" aria-label="第 ${index+1} 行${labels[col]}" placeholder="${isBlank && col===0?'直接输入新词…':''}"/></td>`).join("")}</tr>`
    node("gmBody").innerHTML=items.map(({row,index})=>rowHTML(row,index)).join("")+(page===Math.floor(all.length/200)?rowHTML(newEntry(),virtual,true):"")
    node("gmPage").textContent=`${page+1} / ${Math.floor(all.length/200)+1}`
    node("gmPrev").disabled=page===0;node("gmNext").disabled=page>=Math.floor(all.length/200)
    node("gmSelectAll").checked=items.length>0 && items.every(({index})=>selected.has(index))
    node("gmBody").querySelectorAll("input[data-row]").forEach(input=>{
      input.addEventListener("focus",()=>{ if(activeBefore===null)activeBefore=JSON.stringify(data) })
      input.addEventListener("input",()=>{
        const index=Number(input.dataset.row)
        if(index===entries().length) { if(entries().length>=3000){status("最多保存 3000 条术语",true);input.value="";return};entries().push(newEntry()) }
        entries()[index][keys[Number(input.dataset.col)]]=input.value;dirty=true;chrome()
      })
      input.addEventListener("change",()=>flush())
      input.addEventListener("keydown",event=>{
        if((event.key!=="Tab" && event.key!=="Enter") || event.ctrlKey || event.metaKey)return
        event.preventDefault();let index=Number(input.dataset.row),col=Number(input.dataset.col)
        flush();const order=visible().map(item=>item.index);if(!order.includes(entries().length))order.push(entries().length)
        let pos=order.indexOf(index)
        if(event.key==="Enter")pos+=event.shiftKey?-1:1
        else {col+=event.shiftKey?-1:1;if(col>2){col=0;pos++}if(col<0){col=2;pos--}}
        if(pos>=order.length && entries().length<3000){change(()=>entries().push(newEntry()));order.push(entries().length)}
        table();focusCell(order[Math.max(0,Math.min(pos,order.length-1))],col)
      })
      input.addEventListener("paste",event=>{
        const text=event.clipboardData?.getData("text/plain")||""
        if(text.includes("\t")||text.includes("\n")||text.includes("\r")){event.preventDefault();flush();previewText(text,"\t")}
      })
    })
    node("gmBody").querySelectorAll("[data-select]").forEach(input=>input.addEventListener("change",()=>{const index=Number(input.dataset.select);input.checked?selected.add(index):selected.delete(index);chrome()}))
    node("gmBody").querySelectorAll("[data-restore]").forEach(button=>button.addEventListener("click",()=>change(()=>{entries()[Number(button.dataset.restore)].enabled=true})))
  }
  function modal(title, body, actions) {
    const target=node("gmModal");target.hidden=false
    target.innerHTML=`<section class="gm-dialog" role="dialog" aria-modal="true" aria-label="${escape(title)}"><h2>${escape(title)}</h2>${body}<div class="gm-dialog-actions">${actions.map((action,index)=>`<button data-action="${index}" class="${action.primary?'gm-primary':''}">${escape(action.label)}</button>`).join("")}</div></section>`
    actions.forEach((action,index)=>target.querySelector(`[data-action="${index}"]`).addEventListener("click",action.run))
    target.querySelector("input, textarea, button")?.focus()
  }
  function dismiss() { node("gmModal").hidden=true;node("gmModal").innerHTML="";pending=null }
  function nameLibrary(rename=false) {
    if(rename&&activeLibrary==="local")return
    if(!rename&&(data.libraries||[]).length>=32){status("最多创建 32 个附加术语库",true);return}
    const id=activeLibrary
    modal(rename?"重命名词库":"新建词库",`<label for="gmLibraryInput">词库名称</label><input id="gmLibraryInput" maxlength="40" value="${rename?escape(library().name):''}" placeholder="例如：西门子收放卷"/><p id="gmNameError" class="gm-error" role="alert"></p>`,[
      {label:"取消",run:dismiss},
      {label:rename?"确认重命名":"创建",primary:true,run:()=>{
        const name=node("gmLibraryInput").value.trim()
        if(!name||[...name].length>40||name==="本地术语库"||(data.libraries||[]).some(item=>item.id!==(rename?id:"")&&item.name.toLowerCase()===name.toLowerCase())){node("gmNameError").textContent="名称需唯一且不超过 40 字，本地术语库名称保留";return}
        change(()=>{
          if(rename)data.libraries.find(item=>item.id===id).name=name
          else {const created={id:crypto.randomUUID(),name,enabled:true,entries:[]};(data.libraries||=[]).push(created);activeLibrary=created.id;selected.clear();query="";node("gmSearch").value="";page=0}
        });dismiss()
      }},
    ])
    node("gmLibraryInput").addEventListener("keydown",event=>{if(event.key==="Enter"){event.preventDefault();node("gmModal").querySelector('[data-action="1"]').click()}})
  }
  async function load() {
    try {
      const value=await api.get()
      data=normalize(value)
      saved=fingerprint();loaded=true;dirty=false;history=[];future=[];historyBytes=0;selected.clear();table();chrome()
    } catch(error) { loaded=false;node("gmSave").disabled=true;status(`读取失败：${String(error)}`,true) }
  }
  async function save() {
    flush();if(!loaded||saving)return false;if(!dirty)return true
    const clean = list => list.filter(row=>!empty(row)).map(row=>({...row,source:row.source.trim(),target:row.target.trim(),context:row.context.trim()}))
    const payload={...data,entries:clean(data.entries),libraries:(data.libraries||[]).map(item=>({...item,entries:clean(item.entries)}))}
    for(const item of [{id:"local",name:"本地术语库",entries:payload.entries},...payload.libraries]) {
      const bad=item.entries.findIndex(row=>!row.source||!row.target||[...row.source].length>80||[...row.target].length>80||[...row.context].length>160)
      if(bad>=0){activeLibrary=item.id;table();status(`${item.name}第 ${bad+1} 条需填写原词和译法；两项最多 80 字，语境最多 160 字`,true);return false}
    }
    saving=true;chrome()
    try {
      const output=await api.save(payload)
      data=normalize(output || await api.get());saved=fingerprint();dirty=false;history=[];future=[];historyBytes=0;selected.clear();table();return true
    } catch(error){status(`保存失败：${String(error)}`,true);return false}
    finally {saving=false;root.querySelectorAll(".gm-toolbar,.gm-actions,.gm-table-wrap,.gm-sidebar,.gm-library-title").forEach(element=>{element.inert=false});node("gmReload").disabled=false;node("gmSave").disabled=!dirty;node("gmSave").textContent="保存词库";if(!dirty)chrome()}
  }
  function requestClose() {
    flush();if(saving)return
    if(!dirty){api.close();return}
    modal("有未保存修改","<p>保存后关闭，或放弃本次修改？现有词库不会被自动覆盖。</p>",[
      {label:"继续编辑",run:dismiss},
      {label:"放弃修改",run:()=>{dirty=false;dismiss();api.close()}},
      {label:"保存并关闭",primary:true,run:async()=>{if(await save()){dismiss();api.close()}}},
    ])
  }
  function normalizeImport(rows) {
    const aliases={source:"source","原词":"source",target:"target","译法":"target","参考译法":"target",context:"context","含义":"context","含义／例句":"context","适用语境":"context",source_lang:"source_lang",target_lang:"target_lang",enabled:"enabled"}
    let fields=["source","target","context"],offset=0
    if(rows[0]?.length>=2 && aliases[rows[0][0].trim().toLowerCase()]==="source" && aliases[rows[0][1].trim().toLowerCase()]==="target") {fields=rows[0].map(value=>aliases[value.trim().toLowerCase()]);offset=1}
    const existing=new Set(entries().map(termKey));const added=[];let duplicates=0
    for(let i=offset;i<rows.length;i++) {
      if(rows[i].length>fields.length || rows[i].length<2)throw new Error(`第 ${i+1} 行应至少有原词、译法两列，含义为可选第三列`)
      const entry=newEntry();rows[i].forEach((value,index)=>{if(fields[index])entry[fields[index]]=value.trim()})
      entry.enabled=entry.enabled!==false && entry.enabled!=="false" && entry.enabled!=="0"
      if(!entry.source||!entry.target)throw new Error(`第 ${i+1} 行缺少原词或参考译法`)
      if([...entry.source].length>80||[...entry.target].length>80||[...entry.context].length>160)throw new Error(`第 ${i+1} 行字段过长：原词、译法最多 80 字，含义最多 160 字`)
      if(!["en-zh","zh-en"].includes(`${entry.source_lang}-${entry.target_lang}`))throw new Error(`第 ${i+1} 行的语言方向不受支持`)
      const key=termKey(entry);if(existing.has(key)){duplicates++;continue}existing.add(key);added.push(entry)
    }
    if(entries().length+added.length>3000)throw new Error("导入后超过 3000 条，请分开整理词库")
    return {added,duplicates}
  }
  function previewText(text,delimiter) {
    try {
      flush();const result=normalizeImport(parseTermTable(text,delimiter));pending=result
      const body=`<p>追加 ${result.added.length} 条；跳过 ${result.duplicates} 条完全重复记录。同词不同含义会保留，不覆盖原有词条。</p><div class="gm-preview"><table><thead><tr>${labels.map(label=>`<th>${label}</th>`).join("")}</tr></thead><tbody>${result.added.slice(0,10).map(row=>`<tr>${keys.map(key=>`<td>${escape(row[key])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>${result.added.length>10?"<p>预览前 10 条，其余条目将在追加后显示。</p>":""}`
      modal("确认批量追加",body,[{label:"取消",run:dismiss},{label:`追加 ${result.added.length} 条`,primary:true,run:()=>{const rows=pending.added;dismiss();query="";node("gmSearch").value="";change(()=>entries().push(...rows));status("已追加，请保存词库")}}])
    } catch(error){status(String(error.message||error),true)}
  }

  node("gmNewLibrary").addEventListener("click",()=>nameLibrary())
  node("gmRenameLibrary").addEventListener("click",()=>nameLibrary(true))
  node("gmRemoveLibrary").addEventListener("click",()=>{
    if(activeLibrary==="local")return
    const id=activeLibrary,name=library().name
    modal("删除词库",`<p>删除“${escape(name)}”及其全部词条？保存前可以撤销。</p>`,[{label:"取消",run:dismiss},{label:"删除词库",run:()=>{change(()=>{data.libraries=data.libraries.filter(item=>item.id!==id);activeLibrary="local";selected.clear();page=0});dismiss()}}])
  })
  node("gmSearch").addEventListener("input",()=>{flush();query=node("gmSearch").value.toLowerCase();page=0;selected.clear();table();chrome()})
  node("gmDirection").addEventListener("change",()=>{flush();direction=node("gmDirection").value;page=0;selected.clear();table();chrome()})
  node("gmPrev").addEventListener("click",()=>{flush();page--;table()})
  node("gmNext").addEventListener("click",()=>{flush();page++;table()})
  node("gmEnabled").addEventListener("change",()=>{const checked=node("gmEnabled").checked;change(()=>{data.enabled=checked})})
  node("gmAdd").addEventListener("click",()=>{query="";node("gmSearch").value="";change(()=>{if(entries().length<3000)entries().push(newEntry())});focusCell(entries().length-1,0)})
  node("gmSelectAll").addEventListener("change",()=>{selected=node("gmSelectAll").checked?new Set(visible().map(item=>item.index)):new Set();table();chrome()})
  node("gmDelete").addEventListener("click",()=>{const remove=()=>{change(()=>{setEntries(entries().filter((_,index)=>!selected.has(index)));selected.clear()});dismiss()};if(selected.size>1)modal("删除选中词条",`<p>将删除 ${selected.size} 条词条。保存前可以撤销。</p>`,[{label:"取消",run:dismiss},{label:"删除",run:remove}]);else remove()})
  node("gmUndo").addEventListener("click",()=>undo());node("gmRedo").addEventListener("click",()=>undo(true))
  node("gmSave").addEventListener("click",save)
  node("gmReload").addEventListener("click",()=>{flush();if(dirty)modal("重新载入词库","<p>重新载入将放弃未保存修改。</p>",[{label:"取消",run:dismiss},{label:"放弃并载入",run:()=>{dismiss();load()}}]);else load()})
  node("gmPaste").addEventListener("click",()=>modal("批量粘贴","<p>从 Excel 复制两列或三列并粘贴，下一步预览，不会直接覆盖现有数据。</p><textarea id=\"gmPasteText\" rows=\"9\" placeholder=\"原词 ⇥ 参考译法 ⇥ 含义（可选）\"></textarea>",[{label:"取消",run:dismiss},{label:"预览",primary:true,run:()=>previewText(node("gmPasteText").value,"\t")}]))
  node("gmImport").addEventListener("click",()=>node("gmFile").click())
  node("gmFile").addEventListener("change",async()=>{const file=node("gmFile").files[0];if(!file)return;if(file.size>2_000_000){status("导入文件不能超过 2 MB",true);return}try{const text=await file.text();previewText(text,file.name.toLowerCase().endsWith(".csv")?",":"\t")}catch(error){status(String(error),true)}finally{node("gmFile").value=""}})
  node("gmExport").addEventListener("click",()=>{flush();const quote=value=>'"'+String(value??"").replaceAll('"','""')+'"';const fields=[...keys,"source_lang","target_lang","enabled"];const csv='\uFEFF'+[fields.map(quote).join(","),...entries().filter(row=>!empty(row)).map(row=>fields.map(key=>quote(row[key])).join(","))].join("\r\n");const url=URL.createObjectURL(new Blob([csv],{type:"text/csv;charset=utf-8"}));const a=document.createElement("a");a.href=url;a.download=`PopTrans-${library().name.replace(/[<>:"/\\|?*\x00-\x1f]/g,"-")}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)})
  node("gmClose").addEventListener("click",requestClose)
  api.onClose?.(requestClose)
  root.addEventListener("keydown",event=>{
    if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s"){event.preventDefault();save()}
    else if(node("gmModal").hidden && (event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="z"){event.preventDefault();undo(event.shiftKey)}
    else if(event.key==="Escape"){event.preventDefault();if(!node("gmModal").hidden)dismiss();else requestClose()}
  })
  chrome();load()
  return {requestClose}
}
