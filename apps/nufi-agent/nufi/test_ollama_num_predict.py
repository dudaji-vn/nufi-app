"""The one cap a NuFi box routine can put on a generation.

P2 watched a generation pass 39,000 tokens in one run and 40,000 in another,
still going after the client that asked for it had been killed. The routines
talk to Ollama directly, so LiteLLM's `request_timeout` is not in their path,
and the component's own `Timeout` input is a dead knob: langchain-ollama
0.3.10's ChatOllama has no `timeout` field, so pydantic drops it. `num_predict`
it does have — this pins that the component hands it over.
"""

from lfx_bundles.ollama.ollama import ChatOllamaComponent


def _component(**values):
    c = ChatOllamaComponent()
    for name, value in values.items():
        setattr(c, name, value)
    return c


def test_the_component_offers_a_generation_cap():
    names = [i.name for i in ChatOllamaComponent.inputs]
    assert "num_predict" in names, (
        "a routine has no other way to bound a generation: the model talks to "
        "Ollama directly, and the component's Timeout is dropped by pydantic"
    )


def test_the_cap_reaches_the_model():
    model = _component(base_url="http://localhost:11434", model_name="qwen2.5:7b", num_predict=64).build_model()
    assert model.num_predict == 64


def test_no_cap_leaves_the_model_unbounded_as_before():
    # `or None` is how every other option in this component behaves, and the
    # filter below it drops None: an unset cap must not become num_predict=0,
    # which Ollama reads as "predict nothing".
    model = _component(base_url="http://localhost:11434", model_name="qwen2.5:7b", num_predict=0).build_model()
    assert getattr(model, "num_predict", None) is None
