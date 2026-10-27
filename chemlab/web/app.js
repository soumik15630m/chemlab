"use strict";
const $ = id => document.getElementById(id);
const element = (tag, text, cls) => {const node=document.createElement(tag); if(text!==undefined)node.textContent=text; if(cls)node.className=cls; return node;};
let activeRun=null, timer=null;
async function request(url, options={}){const response=await fetch(url,options); const data=await response.json(); if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail)); return data;}
function message(text,error=false){$("message").textContent=text;$("message").className=error?"error":"";}
function option(select,row){const node=element("option",row.alias+" / "+(row.record.name||row.record.kind));node.value=row.ref;select.append(node);}
async function loadRegistry(){const rows=await request("/api/registry"); for(const id of ["generator","checker","stock"]){$(id).replaceChildren();}
  $("corpus").replaceChildren(element("option","Not configured"));$("corpus").firstChild.value="";
  for(const row of rows){if(row.kind==="model_manifest")option($(row.record.kind==="forward"?"checker":"generator"),row);if(row.kind==="stock")option($("stock"),row);if(row.kind==="corpus"&&row.record.partition!=="final_reference")option($("corpus"),row);}
  if($("corpus").options.length>1)$("corpus").selectedIndex=1;
  const ready=["generator","checker","stock"].every(id=>$(id).options.length);$("submit").disabled=!ready;
  if(!ready)message("Register a generator, forward checker, and stock snapshot using the local CLI before starting a search.");
}
async function loadRuns(){const rows=await request("/api/runs");$("runs").replaceChildren(); for(const row of rows){const button=element("button",row.target.slice(0,22)+" / "+row.state,"run-link");button.type="button";button.onclick=()=>showRun(row.id);$("runs").append(button);}}
function badge(text){return element("span",text.replaceAll("_"," "),"badge "+text);}
function drawTree(route){const nodes=new Map(route.molecules.map(m=>[m.id,m]));const steps=new Map(route.steps.map(s=>[s.product_id,s]));
  function branch(id){const wrapper=element("div",undefined,"tree"), mol=nodes.get(id), step=steps.get(id), card=element("div",undefined,"molecule-card");
    const image=element("img");image.src="/api/molecule.svg?smiles="+encodeURIComponent(mol.molecule.canonical_smiles);image.alt=mol.molecule.canonical_smiles;card.append(image,element("code",mol.molecule.canonical_smiles));card.append(element("small",step?"Intermediate / "+id:"Starting material in stock / "+id));wrapper.append(card);
    if(step){wrapper.append(element("div","Retrosynthetic step "+step.id+" / candidate "+step.candidate_index,"step-label"));for(const child of step.precursor_ids)wrapper.append(branch(child));}return wrapper;}
  return branch(route.root_id);
}
function renderResult(row){const root=$("result");root.className="panel";root.replaceChildren(element("h3",row.target,"result-title"));root.append(badge(row.state));
  if(row.state==="error"){root.append(element("p",row.error||"Run failed."));return;}
  if(row.state!=="complete"){root.append(element("p","Search and verification are running. Results are published only after bundle validation."));return;}
  const result=row.result, run=result.objects[result.run_ref].payload, stats=element("div",undefined,"stats");
  for(const [label,value] of [["Candidate routes",run.search.candidate_routes_found],["Logical expansions",run.search.logical_expansions],["Search model calls",run.search.actual_inferences],["Cache hits",run.search.cache_hits]]){const stat=element("div");stat.append(element("strong",String(value)),element("span",label));stats.append(stat);}root.append(stats);
  root.append(element("p","Search stopped: "+run.search.termination_reason.replaceAll("_"," ")+(run.search.exhausted_limit?" / "+run.search.exhausted_limit:"")));
  if(run.search.error)root.append(element("p",run.search.error,"notice"));
  if(run.experimental)root.append(element("p","Computational fixture run: these records are test data, not model-generated chemical evidence.","notice"));
  const download=element("a","Download complete evidence bundle");download.href="/api/runs/"+row.id+"/bundle";root.append(download);
  const labels={verified_consistent:"Structurally verified / forward consistent",verified_other_evidence:"Structurally verified / conflicting or incomplete forward evidence",availability:"Already in stock",unresolved:"Unresolved routes",rejected:"Rejected diagnostics"};
  for(const [group,items] of Object.entries(result.groups)){if(!items.length)continue;root.append(element("h3",labels[group]));items.forEach((item,index)=>{const route=result.objects[item.route_ref].payload, report=result.objects[item.report_ref].payload,section=element("section",undefined,"route");section.append(element("h3","Route "+(index+1)+" / "+route.steps.length+" reaction steps"));section.append(badge(report.structural_status),badge(report.forward_status));section.append(element("p","Baseline search cost: "+route.search_cost.toFixed(4)+" (lower first)"));
      if(route.steps.length){const retrievals=Object.values(report.precedent).filter(value=>value&&typeof value==="object");const exact=retrievals.filter(value=>value.match_type==="exact_represented_reaction").length;const incomplete=retrievals.filter(value=>value.status!=="pass").length;section.append(element("p","Exact represented precedent: "+exact+" of "+route.steps.length+" steps."+(incomplete?" Retrieval incomplete for "+incomplete+" steps.":" Unmatched steps have no exact precedent in this corpus."),"notice"));}
      if(group!=="rejected")section.append(drawTree(route));const details=element("details"), table=element("table");details.append(element("summary","Inspect checks and reaction evidence"));const head=element("tr");for(const label of ["Check","Outcome","Reason"])head.append(element("th",label));table.append(head);
      for(const check of report.checks){const tr=element("tr"),status=element("td");status.append(badge(check.status));tr.append(element("td",check.name),status,element("td",check.reason));table.append(tr);}details.append(table,element("pre",JSON.stringify({mapping:report.mapping_coverage,precedent:report.precedent},null,2)));section.append(details);root.append(section);});}
  root.append(element("p","Structural checks and forward agreement do not prove experimental feasibility. Inspect unsupported or conflicting steps before drawing a chemical conclusion.","fine"));
}
async function showRun(id){activeRun=id;clearTimeout(timer);try{const row=await request("/api/runs/"+id);renderResult(row);if(["queued","running"].includes(row.state))timer=setTimeout(()=>showRun(id),2000);else await loadRuns();}catch(error){message(error.message,true);}}
$("search-form").onsubmit=async event=>{event.preventDefault();$("submit").disabled=true;try{const config={backward_manifest:$("generator").value,forward_manifest:$("checker").value,stock_ref:$("stock").value,corpus_ref:$("corpus").value||null,prediction_count:Number($("predictions").value),forward_k:Number($("forward-k").value),logical_expansion_limit:Number($("expansions").value),route_limit:Number($("routes").value),max_depth:Number($("depth").value),seed:Number($("seed").value),mapping_profile:$("profile").value,full_diagnostics:$("diagnostics").checked};const row=await request("/api/runs",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({target:$("target").value.trim(),config})});message("Search queued. Every candidate route will be independently checked.");await loadRuns();await showRun(row.id);}catch(error){message(error.message,true);}finally{$("submit").disabled=false;}};
$("stock-form").onsubmit=async event=>{event.preventDefault();try{await request("/api/stocks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({alias:$("stock-name").value,smiles:$("stock-smiles").value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean),source:$("stock-source").value,license:$("stock-license").value})});await loadRegistry();message("Stock snapshot saved.");}catch(error){message(error.message,true);}};
$("refresh").onclick=()=>loadRuns().catch(error=>message(error.message,true));
$("target").onchange=()=>{const image=element("img");image.alt="Target molecule preview";image.src="/api/molecule.svg?smiles="+encodeURIComponent($("target").value.trim());image.onerror=()=>$("preview").replaceChildren();$("preview").replaceChildren(image);};
Promise.all([loadRegistry(),loadRuns()]).catch(error=>message(error.message,true));
