def build_master_schema(manifests: list) -> dict:
    all_top_k = list(
        {
            feat
            for m in manifests
            for feat in m["feature_schema"].get("top_k_features", [])
        }
    )

    fv_props = {feat: {"type": "NUMBER"} for feat in all_top_k}

    item_schema = {
        "type": "object",
        "properties": {
            "model_id": {"type": "string"},
            "final_feature_vector": {"type": "object", "properties": fv_props},
        },
        "required": ["model_id", "final_feature_vector"],
    }

    return {
        "type": "object",
        "properties": {
            # ── metadata for LLM 2 only — never used for routing ──
            "execution_mode": {
                "type": "string",
                "enum": ["single", "multi_model", "multi_instance", "ambiguous"],
            },
            "model_id": {"type": "string"},  # primary model label for LLM 2
            "fallback_question": {"type": "string"},
            # ── the only thing the orchestrator iterates ──
            "items": {"type": "array", "items": item_schema},
        },
        "required": ["execution_mode", "items"],
    }


def build_master_prompt(manifests: list) -> str:

    registry_lines = ["AVAILABLE MODELS:\n"]
    for m in manifests:
        schema = m["feature_schema"]
        hints = m["llm_hints"]
        top_k = schema.get("top_k_features", [])
        feat_types = schema.get("feature_types", {})
        entity_map = hints.get("entity_map", {})
        triggers = ", ".join(hints["trigger_phrases"])

        feat_lines = []
        for feat in top_k:
            ftype = feat_types.get(feat, "numeric")
            aliases = ", ".join(entity_map.get(feat, [feat]))
            feat_lines.append(f"    {feat:<28} ({ftype}) → {aliases}")

        registry_lines.append(f"MODEL_ID    : {m['model_id']}")
        registry_lines.append(f"TASK        : {m['task']}")
        registry_lines.append(f"DESCRIPTION : {m['description']}")
        registry_lines.append(f"TRIGGERS    : {triggers}")
        registry_lines.append("TOP-K FEATURES:")
        registry_lines.extend(feat_lines)
        registry_lines.append(f"FALLBACK    : {hints['ambiguous_fallback']}")
        registry_lines.append("---")

    registry_text = "\n".join(registry_lines)

    return f"""You are an ML model router and feature extractor.

{registry_text}

══ JOB 1 — ROUTE ══
Set execution_mode (label only — describes what you're doing):
  single         → one model, one input
  multi_model    → two different models
  multi_instance → same model, different inputs (X vs Y)
  ambiguous      → cannot determine intent

Set model_id to the primary model used (for explanation purposes).

ROUTING RULES:
1. Exact trigger match, one model         → single
2. Strong semantic match, one model       → single
3. Two DIFFERENT models clearly needed    → multi_model
4. SAME model, DIFFERENT inputs (X vs Y) → multi_instance
5. Cannot determine intent                → ambiguous

If ambiguous → set execution_mode = ambiguous, populate fallback_question,
and return items = [].

══ JOB 2 — BUILD items[] ══
Always populate items[] — this is what the backend iterates.
Each item has: model_id, final_feature_vector.

  single         → items has ONE entry, no instance_id needed
  multi_model    → items has ONE entry per model, each with its own model_id
  multi_instance → items has ONE entry per instance, same model_id on each

MULTI-INSTANCE SIGNALS: "vs", "versus", "compared to", "and also",
"for both", comma-separated values for the SAME feature.

══ JOB 3 — EXTRACT final_feature_vector FOR EACH ITEM ══
For each item in items[], populate its final_feature_vector.

STEP-BY-STEP EXTRACTION PROCESS:
Step 1 — Read the user query carefully word by word
Step 2 — For each top-k feature, ask: "Did the user explicitly mention this?"
          YES → extract the exact value the user provided
          NO  → do NOT fill it, do NOT guess, do NOT use 0
Step 3 — Only populate features the user explicitly mentioned
Step 4 — Leave everything else for the backend imputer to fill

══ CRITICAL RULES ══

RULE 1 — NEVER INVENT VALUES:
- Only extract what the user explicitly said
- If a feature is not in the query → omit it entirely from final_feature_vector
- The backend imputer will fill all missing features from training data

RULE 2 — NULL vs ZERO (MOST IMPORTANT):
- 0 is a real business value (e.g. zero installments, zero price)
- ONLY use 0 if the user explicitly said "zero", "0", "none", "no installments"
- If the user did not mention a feature → omit it (backend fills it)
- NEVER use 0 as a placeholder for "not mentioned"

RULE 3 — BINARY FEATURES:
- is_installment = 1 → user said "installments" / "EMI" / "X parts"
- is_installment = 0 → user said "single payment" / "one shot" / "no installments"
- is_installment     → omit entirely if user said nothing about payment method

RULE 4 — NEVER COMPUTE DERIVED FEATURES:
- Never compute or guess volume_cm3, freight_ratio, price_per_gram, distance_km
- Backend computes these from raw inputs after extraction

══ ALIAS RESOLUTION ══

GENERAL:


- "item costs X" / "priced at X" / "costs X"        → price = X
- "freight X" / "shipping X" / "delivery charge X"  → freight_value = X
- "next X days"                                      → horizon_days = X
- "next X weeks"                                     → horizon_days = X × 7
- "next X months"                                    → horizon_days = X × 30


══ DERIVED FEATURE RULES ══
These features are NEVER computed by you — backend handles them.
Only extract if the user states the value directly and explicitly:
  volume_cm3     → only if user says "volume is X cm³"
  freight_ratio  → only if user says "freight ratio is X"
  price_per_gram → only if user says "price per gram is X"
  distance_km    → only if user says "distance is X km"

══ EXAMPLES ══

Query: "Estimate freight for an item priced at 6000 BRL"
Route  : freight_regressor
Correct extraction:
  price = 6000
  (all other features omitted — imputer fills them)


Query: "A product weighing 300g, priced at 150 BRL — what category is it?"
Route  : category_classifier
Correct extraction:
  product_weight_g = 300
  price            = 150
  (all other features omitted — imputer fills them)

Query: "What category for a 500g item costing 200 BRL with shipping cost 25 BRL?"
Route  : category_classifier
Correct extraction:
  product_weight_g = 500
  price            = 200
  freight_value    = 25
  (all other features omitted — imputer fills them)

Query: "Estimate freight for a 400g item vs a 900g item, both priced at 80 BRL"
Route  : freight_regressor, multi_instance
Item 1 extraction:
  product_weight_g = 400
  price            = 80
Item 2 extraction:
  product_weight_g = 900
  price            = 80

Query: "What category is this product AND what will freight cost? It weighs 600g, priced at 300 BRL"
Route  : multi_model
Item 1 (category_classifier):
  product_weight_g = 600
  price            = 300
Item 2 (freight_regressor):
  product_weight_g = 600
  price            = 300"""


def build_response_prompt(
    user_query: str,
    feature_table: str,
) -> str:

    return f"""You are a business language writer for an ML inference tool.
The model has run. Write a plain English explanation for the user.

USER QUERY: {user_query}

FEATURE TABLE (inputs, task, and prediction result):
{feature_table}

RULES:
- Read the Feature Table — it has everything you need
- Write a clear, confident business answer in 1 to 4 sentences
- Use plain English — no technical terms, model names, or jargon
- State the result naturally, as a business insight not a model output
- For regression results: state the predicted value and note it is an estimate
- For classification results: state the predicted category and top confidence if available
- Include the predicted value and range where relevant
- Do NOT include a feature table or raw input table in the response
- For forecasting results: If the user is asking for particular date directly then result for date should be stated,state the total and peak, then note the daily breakdown table is shown below.
- Do NOT summarise the daily table — it is already rendered for the user"""
