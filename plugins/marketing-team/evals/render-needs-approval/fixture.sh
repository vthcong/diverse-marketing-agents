#!/usr/bin/env bash
# Seeds the empty eval workspace with the files the lead would have written before the scout and producer run
mkdir -p workspace/demo
cat > workspace/demo/brief.md <<'EOF'
# Brief: Ember Roasters cold brew
- Deliverables: one Instagram post and one avatar video
- Platform: Instagram
- Audience: commuters who want coffee without the bitterness
- Tone: warm, plain, a little playful
- Constraints: no prices, no health claims, no statistics
EOF
cat > workspace/demo/chosen.md <<'EOF'
Mornings shouldn't start with a fight against a bitter cup. Our new cold brew is steeped slowly so every sip lands smooth and rich, with no sugar added. Pour it over ice, add a splash of milk, or drink it straight from the bottle. Find it at Ember Roasters this week.
EOF
