#!/usr/bin/env python3
"""What the four routines are made of, checked without a Studio.

    python3 studio/test_flows.py        # from deploy/platform/scenarios

Every assertion here is about the JSON that goes over the wire: the components
in each recipe, the drive path they read, the k they retrieve, and the prompt
variable the retrieved passages land in. Those are exactly the things that fail
silently -- a flow with a missing prompt field POSTs 201, opens in the canvas,
and answers out of thin air because the documents edge had nothing to bind to.

The catalogue in testdata/ is the real one, pulled from a box's own
/api/v1/all with the component code bodies trimmed out; the builder only reads
the templates.
"""
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import build_flows as bf  # noqa: E402
import run_flows as rf  # noqa: E402

CATALOG = json.loads((HERE / "testdata" / "catalog.json").read_text())
OPTS = {"model": "qwen2.5:7b", "ollama": "http://host.docker.internal:11434",
        "embeddings": "bge-m3", "drives_root": "/drives", "department": "legal"}
RECIPE_IDS = ["docqa", "meeting", "helpdesk", "weekly"]

failures = []


def check(name, condition, detail=""):
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}  {detail}")
        failures.append(name)


def spec(recipe_id):
    return next(s for s in bf.RECIPES if s["id"] == recipe_id)


def graph(recipe_id, opts=None):
    flow, dept, path = bf.build_recipe(CATALOG, spec(recipe_id), opts or OPTS)
    nodes = {n["id"]: n for n in flow["data"]["nodes"]}
    edges = {(e["source"], e["data"]["targetHandle"]["fieldName"]): e["target"]
             for e in flow["data"]["edges"]}
    return flow, nodes, edges, dept, path


def field(nodes, node_id, name):
    return nodes[node_id]["data"]["node"]["template"][name]["value"]


def test_the_four_recipes_exist():
    check("four recipes are defined", [s["id"] for s in bf.RECIPES] == RECIPE_IDS,
          [s["id"] for s in bf.RECIPES])
    saved = json.loads((HERE / "flows.json").read_text())
    for rid in RECIPE_IDS:
        check(f"flows.json has {rid}", rid in saved and saved[rid].get("id"))
    for rid in ("docqa", "helpdesk", "weekly"):
        drive = saved.get(rid, {}).get("drive", {})
        check(f"flows.json records {rid}'s drive path",
              str(drive.get("path", "")).startswith("/drives/"), drive)


def test_document_flows_read_the_drive():
    for rid, dept in (("docqa", "legal"), ("helpdesk", "hr"), ("weekly", "legal")):
        _flow, nodes, edges, got_dept, path = graph(rid)
        check(f"{rid} reads /drives/{dept}", path == f"/drives/{dept}" and got_dept == dept,
              path)
        check(f"{rid} points its Directory at the drive",
              field(nodes, bf.DRIVE_NODE, "path") == f"/drives/{dept}")
        check(f"{rid} walks the whole drive", field(nodes, bf.DRIVE_NODE, "recursive") is True)
        # The file name has to reach the model or "cite the file" cannot work.
        check(f"{rid} carries the file name with the passage",
              "{file_path}" in field(nodes, "ParseDataFrame-passages", "template"))
        check(f"{rid} wires the passages into the prompt",
              edges.get(("ParseDataFrame-passages", "documents")) == "Prompt-sys")
        prompt = nodes["Prompt-sys"]["data"]["node"]
        check(f"{rid} declares the documents variable",
              prompt["template"].get("documents", {}).get("input_types") == ["Message"]
              and prompt.get("custom_fields") == {"template": ["documents"]})
        check(f"{rid} answers with the on-box model",
              field(nodes, "ChatOllama-llm", "base_url") == OPTS["ollama"]
              and field(nodes, "ChatOllama-llm", "model_name") == "qwen2.5:7b")


def test_retrieval_flows_index_per_department():
    for rid, dept in (("docqa", "legal"), ("helpdesk", "hr")):
        _flow, nodes, edges, _d, _p = graph(rid)
        check(f"{rid} retrieves four passages",
              field(nodes, bf.INDEX_NODE, "number_of_results") == 4)
        check(f"{rid} keeps a collection per department",
              field(nodes, bf.INDEX_NODE, "collection_name") == f"nufi-{dept}")
        check(f"{rid} embeds on the box",
              field(nodes, "OllamaEmbeddings-embed", "model_name") == "bge-m3"
              and field(nodes, "OllamaEmbeddings-embed", "base_url") == OPTS["ollama"])
        check(f"{rid} chunks before it embeds",
              edges.get(("Directory-drive", "data_inputs")) == "SplitText-chunks"
              and edges.get(("SplitText-chunks", "ingest_data")) == bf.INDEX_NODE)
        check(f"{rid} searches with the question",
              edges.get(("ChatInput-in", "search_query")) == bf.INDEX_NODE)
        # Ingest ships visible and Retrieve hidden; a wired-but-invisible field
        # is a flow nobody can understand by opening it.
        for hidden in ("search_query", "number_of_results"):
            check(f"{rid} shows {hidden} on the canvas",
                  nodes[bf.INDEX_NODE]["data"]["node"]["template"][hidden]["show"] is True)


def test_weekly_reads_without_a_vector_store():
    _flow, nodes, edges, _d, _p = graph("weekly")
    check("weekly has no index", bf.INDEX_NODE not in nodes)
    check("weekly reads the drive straight into the prompt",
          edges.get(("Directory-drive", "df")) == "ParseDataFrame-passages")


def test_nothing_in_a_recipe_can_bound_the_generation():
    """Defect D2 of the P2 acceptance, pinned where it is decided.

    `weekly` never came back: 39,000 tokens on a 4,096-token context, still
    climbing after its client had been killed, starving every other question
    on the box. The cap belongs at this node — the recipe knows a weekly report
    is a few hundred tokens — and it cannot be set here:

      * the Ollama component the recipes use has no `num_predict` input, and
        its build_model() never passes one, although langchain-ollama's
        ChatOllama has the field (verified against the pinned 0.3.10);
      * the one input that looks like a deadline, `timeout`, is dropped on the
        floor: the component sets it in llm_params, and ChatOllama has no such
        field, so pydantic ignores it and nothing reaches Ollama;
      * and the recipes talk to Ollama directly, so LiteLLM's own
        `request_timeout: 600` — the box's other bound — is not in this path.

    So the fix is a change to the Studio image (apps/nufi-agent), outside the
    box branch. When that component grows an output cap, this check fails and
    build_recipe should start setting it.
    """
    template = CATALOG["ollama"][bf.OLLAMA]["template"]
    caps = [k for k in template
            if k in ("num_predict", "max_tokens", "max_output_tokens", "max_completion_tokens")]
    check("the recipes' model component still exposes no output cap "
          "(set one in build_recipe when it does)", not caps, caps)
    _flow, nodes, _e, _d, _p = graph("weekly")
    check("weekly's model node is the Ollama one, decoding greedily",
          nodes["ChatOllama-llm"]["data"]["type"] == bf.OLLAMA
          and field(nodes, "ChatOllama-llm", "temperature") == 0
          and field(nodes, "ChatOllama-llm", "top_k") == 1)


def test_a_routine_that_does_not_come_back_says_so():
    """The runner used to let a socket timeout out as a traceback, which reads
    like the tool broke. It did not: the box is still generating, and giving up
    here does not stop it."""
    saved = json.loads((HERE / "flows.json").read_text())
    original = rf.OPEN

    def never_answers(_req, timeout=400):
        raise TimeoutError("timed out")

    rf.OPEN = never_answers
    try:
        code, out = rf.run("https://box:7860", "sk-x", saved["weekly"]["id"], "hi", timeout=3)
    finally:
        rf.OPEN = original
    check("a timeout is a result, not an exception", code == 0, code)
    check("it says the box is probably still generating",
          "still generating" in out and "ollama stop" in out, out)


def test_meeting_is_a_transcript_flow():
    s = spec("meeting")
    check("meeting takes the transcript as chat input", s["kind"] == "prompt")
    flow = bf.build(CATALOG, s, "qwen2.5:7b", OPTS["ollama"])
    types = [n["data"]["type"] for n in flow["data"]["nodes"]]
    check("meeting is input -> prompt -> model -> output",
          types == ["ChatInput", "Prompt", bf.OLLAMA, "ChatOutput"], types)
    for word in ("결정사항", "담당자", "기한"):
        check(f"meeting asks for {word}", word in s["system"])


def test_the_department_is_a_tweak():
    saved = json.loads((HERE / "flows.json").read_text())
    tw = rf.tweaks_for(saved["docqa"], "finance")
    check("a tweak moves the drive",
          tw.get(bf.DRIVE_NODE, {}).get("path") == "/drives/finance", tw)
    check("a tweak moves the index with it",
          tw.get(bf.INDEX_NODE, {}).get("collection_name") == "nufi-finance", tw)
    check("no department, no tweak", rf.tweaks_for(saved["docqa"], "") == {})
    check("the HR helpdesk stays on the HR drive",
          rf.tweaks_for(saved["helpdesk"], "finance") == {})


def test_a_different_box_gets_different_paths():
    opts = dict(OPTS, drives_root="/srv/drives", department="finance")
    _flow, nodes, _e, dept, path = graph("docqa", opts)
    check("the drives root is not hard-coded", path == "/srv/drives/finance", path)
    check("the department is not hard-coded", dept == "finance")
    check("the collection follows the department",
          field(nodes, bf.INDEX_NODE, "collection_name") == "nufi-finance")
    # helpdesk names its drive itself: an HR policy answer out of the finance
    # drive would be worse than no answer.
    _f, _n, _e2, hr_dept, hr_path = graph("helpdesk", opts)
    check("the HR helpdesk keeps its own drive",
          (hr_dept, hr_path) == ("hr", "/srv/drives/hr"), hr_path)


def test_dry_run_prints_the_recipes():
    out = subprocess.run(
        [sys.executable, str(HERE / "build_flows.py"), "--box", "https://localhost:7860",
         "--drives-root", "/drives", "--departments", "legal,hr", "--dry-run"],
        capture_output=True, text=True, check=True).stdout
    for rid in RECIPE_IDS:
        check(f"--dry-run names {rid}", rid in out)
    check("--dry-run shows the drive path", "Directory(/drives/legal)" in out, out[-200:])
    check("--dry-run shows the retrieval k", "LocalDB(k=4, nufi-hr)" in out)
    check("--dry-run reaches no Studio", "http" in out and "Traceback" not in out)


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            print(name)
            fn()
    print(f"\n{len(failures)} failure(s)" if failures else "\nall checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
