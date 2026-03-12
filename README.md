# Library Due

List checked out library items and due dates from the Ramsey County Library website.
It should be possible to adapt this code to other libraries that use BiblioCommons,
but I have not tested this.

# Requirements

Python 3.9+ is required. The code was developed and tested using Python 3.14.3.

The Firefox browser is required, but you can modify the code to use a different browser.

# Installation

1. Clone the repository (or download the archive and unzip):

   ```bash
   git clone https://github.com/Radcliffe/library_due.git
   cd library_due
    ```
2. Create a virtual environment and activate it:

   ```bash
   python3 -m venv env
   source env/bin/activate  # On Windows: env\Scripts\activate
    ```
3. Install the required dependencies:

    ```bash
    pip install -r requirements.txt
     ```
4. Set up Playwright and the Firefox browser:

   ```bash
   playwright install firefox
    ```
5. Create a `.env` file in the project root directory and add your library account credentials:

   ```
   LIBRARY_USERNAME=your_username
   LIBRARY_PIN=your_password
    ```

If the `.env` file is not present, the script will use the `LIBRARY_USERNAME` and `LIBRARY_PIN` environment variables if they are set.

# Usage
Run the script to list your checked-out library items and their due dates:

```bash
python library_due.py
```

The script launches the Firefox browser (invisibly) and logs into your library account using your login credentials.
This may take up to 30 seconds, so be patient.

## Options

- `--headed`: Run the browser in headed mode (default: False).
- `--json`: Output the results in JSON format (default: False).
- `--debug-html checkedout.html`: Save the HTML of the checked-out items page for debugging purposes.
- `--input-html checkedout.html`: Use a saved HTML file instead of fetching it from the website (useful for testing).
- `--state-file .library_state.json`: Save the browser session to a file for reuse in future runs.

# License

This project is licensed under the MIT License. See the [LICENSE.md](LICENSE.md) file for details.