# Library Due

List checked out library items and due dates from the Ramsey County Library website.
It should be possible to adapt this code to other libraries that use BiblioCommons,
but I have not tested this.

# Requirements

Python 3.9+ is required. The code was developed and tested using Python 3.14.3.

The Firefox browser is required, but you can modify the code to use a different browser.

# Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Radcliffe/library_due.git
   cd library_due
    ```
2. Create a virtual environment and activate it:

   ```bash
   python -m venv env
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

# Usage
Run the script to list your checked-out library items and their due dates:

```bash
python library_due.py
```

## Options

- `--headed`: Run the browser in headed mode (default: False).
- `--json`: Output the results in JSON format (default: False).
- `--debug-html checkedout.html`: Save the HTML of the checked-out items page for debugging purposes.
- `--state-file .library_state.json`: Save the browser session to a file for reuse in future runs.


