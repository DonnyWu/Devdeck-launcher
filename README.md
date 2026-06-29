# DevDeck

A desktop control panel for the local web apps in your projects folder (the
folder that contains DevDeck; override with the `DEVDECK_BASE_DIR` environment
variable). One row per project with an on/off toggle, a green/red status light,
an auto-picked free port + clickable URL, and a live side panel of CPU / RAM /
uptime for whatever is running.

Turning a project **on** detects its type, finds a free port, and launches it in
the background. Turning it **off** kills the entire process tree and frees the
port.

## What it manages

Auto-discovered web projects (desktop/CLI projects are ignored):

| Type | Detected by | Launched as |
|------|-------------|-------------|
| Streamlit | `app.py` + `streamlit` in requirements | `python -m streamlit run app.py --server.port <P> --server.headless true` |
| Gradio | `app.py` + `gradio` in requirements | `python app.py` with `GRADIO_SERVER_PORT=<P>` |
| Node / Vite | `package.json` with a `dev` script | `npm run dev -- --port <P>` |
| React / Node | `package.json` `start` script | `npm run start` with `PORT=<P>` |
| ASP.NET | `*.csproj` using `Microsoft.NET.Sdk.Web` | `dotnet run --project <csproj> --urls http://localhost:<P>` |
| Static | `index.html` | `python -m http.server <P>` |

Streamlit/Gradio prefer the project's own `.venv\Scripts\python.exe` when present.

> DevDeck is only the manager. It drives the toolchains already installed on this
> machine (each project's `.venv`, system `python`, `npm`/`node`, `dotnet`) - it
> does not bundle them. If a project's dependencies or `.env` aren't set up, the
> light goes red and the **Log** button shows the real error.

## Run from source

```powershell
cd path\to\DevDeck
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m devdeck.main
```

## Build the .exe

```powershell
.\build.ps1
```

Produces `dist\DevDeck\DevDeck.exe`. Double-click to run; pin a shortcut if you
like. For a single portable file, re-run PyInstaller with `--onefile`.

## Notes

- **Closing DevDeck leaves servers running** and re-adopts them on next launch
  (state is kept in `%APPDATA%\DevDeck\state.json`). Use **Stop all** to shut
  everything down, or each row's toggle.
- Per-app logs live in `%APPDATA%\DevDeck\logs\`.
- CPU% is summed across the process tree and can exceed 100% on multi-core.
