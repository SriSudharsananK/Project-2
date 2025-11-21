# Project-2: LLM API Quiz Solver

This project implements a FastAPI endpoint that receives quiz challenges, solves them using a headless browser and data analysis libraries, and submits the answers.

## Setup

1.  **Install Dependencies:**
    Make sure you have Python 3.8+ installed. Then, install the required packages:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Install Playwright Browsers:**
    Playwright needs to download browser binaries. Run the following command:
    ```bash
    python -m playwright install
    ```

3.  **Create `.env` file:**
    Create a `.env` file in the root of the project and add your secret:
    ```
    SECRET=your_actual_secret
    ```
    Replace `your_actual_secret` with the secret you will be using.

## How to Run

1.  **Start the server:**
    Use `uvicorn` to run the FastAPI application:
    ```bash
    uvicorn main:app --reload
    ```
    The server will be running at `http://127.0.0.1:8000`. When running, you will see timestamped log messages in this terminal.

2.  **Test the endpoint:**
    To test the endpoint, you will need to send it a POST request. The easiest way to do this from the command line is by using a `payload.json` file.

    **a. Create `payload.json`:**
    Create a file named `payload.json` with the following content:
    ```json
    {
      "email": "your.email@example.com",
      "secret": "your_actual_secret",
      "url": "https://tds-llm-analysis.s-anand.net/demo"
    }
    ```
    Make sure to replace `your_actual_secret` with the secret from your `.env` file.

    **b. Send the request using `curl`:**
    Open a **new terminal** and run the following command:
    ```bash
    curl -X POST "http://127.0.0.1:8000/quiz" -H "Content-Type: application/json" --data "@payload.json"
    ```

    After sending the request, switch back to the terminal where `uvicorn` is running to see the detailed log output of the quiz-solving process.

## How it works

1.  The `main.py` script starts a FastAPI server.
2.  The `/quiz` endpoint receives a POST request with an `email`, `secret`, and a `url`.
3.  It validates the `secret` and, if valid, starts a background task to solve the quiz. This allows the API to respond with a `200 OK` immediately.
4.  The `solve_quiz` function in the background task does the following:
    *   Launches a headless Chromium browser using Playwright.
    *   Navigates to the provided `url`.
    *   It scrapes the page to find the question, any data files, and the URL to submit the answer to. It's designed to handle the provided example where the question is base64 encoded in a script tag.
    *   It then processes the data to find the answer. The current implementation is tailored to solve the example quiz (download a PDF, read a table, and sum a column).
    *   It submits the answer to the submission URL.
    *   If the answer is correct and a new quiz URL is provided, it calls itself recursively to solve the next quiz.
    *   If the answer is incorrect or the quiz is over, it stops and logs the result.
5.  **Logging and Error Handling:** The application uses Python's `logging` module to provide detailed, timestamped output. It also includes specific `try...except` blocks to handle potential errors gracefully during various stages like web navigation, data processing, and API requests, making the system more robust and easier to debug.