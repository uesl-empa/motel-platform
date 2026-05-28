# Streamlit App

This app provides an interactive view of MOTEL sample technology parameters.

## Run locally

```bash
cd streamlit
python -m venv .venv
source .venv/bin/activate  # On Windows use: .venv\\Scripts\\activate
pip install -r requirements.txt
streamlit run app.py
```

The app intentionally reads from `streamlit/data/` for Streamlit Community Cloud compatibility.
