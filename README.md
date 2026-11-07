# BREADY — NOVA Hackathon

Integrated team application: unified order intake, kitchen prioritization and individual tickets, AI communication, packing verification, and front-desk handoff.

## Launch

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

The canonical application lives in `rushready/`. Running `streamlit run app.py` there also works. Both entry points use the same SQLite store and existing `RUSHREADY_DB` override. Configuration and credential names remain unchanged.

## Tests

```bash
python3 -m pytest rushready/tests -q
cd rushready/kitchen-display
npm test
```

The kitchen display browser prototype remains available separately with `npm start`; it has its own in-memory demo data and is not the Streamlit order store.

See [application documentation](rushready/README.md) and [team integration guide](TEAM_INTEGRATION_GUIDE.md) for feature ownership and setup. The app uses simulated platform orders; no DoorDash or Uber Eats API is connected.
