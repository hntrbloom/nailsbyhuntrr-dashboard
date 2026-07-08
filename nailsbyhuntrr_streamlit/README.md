# NailsByHuntrr Streamlit Dashboard

Phone-friendly Streamlit dashboard for managing Etsy inventory, colors, sales, and revenue.

## Run it

```powershell
cd "C:\Users\heblo\Documents\Codex\2026-07-07\ca\outputs\nailsbyhuntrr_streamlit"
python -m pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0
```

Open the local URL on your computer, or open the network URL on your phone while both devices are on the same Wi-Fi.

The app creates `nailsbyhuntrr.db` in this folder and seeds it with sample nails, keychains, colors, and sales the first time it runs.

## Deploy to Streamlit Community Cloud

1. Create a GitHub repository, for example `nailsbyhuntrr-dashboard`.
2. Upload these project files to the repository:
   - `app.py`
   - `requirements.txt`
   - `README.md`
   - `.gitignore`
3. Do not upload `nailsbyhuntrr.db`; it contains local dashboard data and may contain private Etsy API tokens.
4. In Streamlit Community Cloud, choose the GitHub repository and set the main file path to:

```text
app.py
```

The deployed app will create its own empty SQLite database. For long-term production use, move the data to a hosted database because Streamlit Community Cloud storage can reset when the app rebuilds.
