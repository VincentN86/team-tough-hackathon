# BREADY (formerly RushReady) — NOVA Front House Hackathon

A functional **demo** of unified restaurant order intake, deadline-based kitchen prioritization, a chef-to-server OpenRouter incident agent, and human-confirmed packing/handoff. No real DoorDash/Uber Eats connectivity, customer messaging, or trained preparation-time model is included.

## Start in VS Code

1. Unzip this project and open the **`nova-rushready-v2`** folder in VS Code.
2. In VS Code's menu choose **Terminal → New Terminal**.
3. Run:

   ```bash
   python3 -m pip install -r requirements.txt
   python3 -m streamlit run app.py
   ```

4. Open the local browser URL shown in Terminal, usually `http://localhost:8501`.

If installation fails because Python is externally managed, use a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Windows activation: `.venv\Scripts\activate`.

## OpenRouter setup (optional)

You can use the demo without an API key: the typed chef report uses a simple keyword parser. To enable real AI extraction and optional microphone/photo functions:

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Add your OpenRouter key and a **permitted** chat model:

   ```toml
   OPENROUTER_API_KEY = "YOUR_PRIVATE_KEY"
   OPENROUTER_MODEL = "openrouter/auto"
   ```

3. `.gitignore` excludes `secrets.toml`. **Never commit the key**.
4. Your sponsor key might have access only to specific models. If a request fails, check the organizer's authorized model list and remaining credits. The speech-to-text feature separately defaults to `openai/whisper-1` and may not be included in the sponsor key. Photo checking requires a **vision-capable** model.

API source documents:
- [OpenRouter chat completions](https://openrouter.ai/docs/api-reference/chat-completion)
- [OpenRouter image input](https://openrouter.ai/blog/tutorials/send-image-to-llm/)
- [OpenRouter transcription](https://openrouter.ai/blog/tutorials/transcription-on-openrouter/)

## Suggested two-minute judges' demo

1. **Intake:** See DoorDash, Uber Eats, website, and POS orders in one feed. Add a new Phone order.
2. **Cook:** Show that the deadline-based queue prioritizes long-prep items; show station-specific tickets and batch hints.
3. **AI agent:** With a key configured, enter or record `We are out of chicken. The fryer is running 10 minutes behind.`; review the detected facts, then **Confirm and notify Front Desk**.
4. **Front Desk:** Show which orders are blocked or delayed, revised readiness estimates, and *suggested* messages for staff. Nothing is actually sent.
5. **Cook and Packer:** Resolve the incident, mark each item ready, tick packer checkboxes, manually confirm any modifiers and allergies, then seal the order.
6. **Front Desk:** Mark the packed order handed off.

## Architecture

- `app.py`: Streamlit interface: Intake, Cook, Packer, Front Desk, Workflow.
- `database.py`: shared SQLite demo database and validated state transitions.
- `scheduler.py`: transparent preparation estimates, priority and issue impacts.
- `ai_agent.py`: OpenRouter chef text parsing, optional audio transcription and photo review.
- `tests/test_logic.py`: tests for source intake, incident effects, human confirmation and priority sorting.

The shared SQLite database is created as `rushready.db`, excluded from Git. It is usable for simultaneous browser sessions on **one** running server. SQLite files are not guaranteed to persist across Cloud restarts and are not suitable for a real restaurant service. For durable multi-instance deployment, replace `database.py` with Postgres/Supabase and add role authentication and audit logs.

This app polls for changes approximately every 5 seconds while a browser tab is active. It does not currently connect to real delivery services, send push notifications, train a machine-learning prediction model, or safely infer allergens from photos.

## GitHub

Create a new empty GitHub repository (for example `nova-rushready-v2`). In this folder run:

```bash
git init
git add .
git commit -m "Build Front House hackathon demo"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/nova-rushready-v2.git
git push -u origin main
```

Use feature branches if teammates work on overlapping files. Before merging, run `python3 -m pytest -q` if pytest is installed. Then deploy via [Streamlit Community Cloud](https://share.streamlit.io/) by selecting `app.py` and entering `OPENROUTER_API_KEY` in **Advanced settings → Secrets**. No key is necessary to deploy the rule-based demo.

**Data/privacy:** Use only fictional customers/orders during the hackathon. Don't send real customer details or allergy records to an LLM. This is a prototype, not a validated production food-safety system.
