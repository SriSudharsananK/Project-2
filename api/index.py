import os
import asyncio
import base64
import json
import logging
import re
from typing import Optional, Union, Dict, Any

import fitz  # PyMuPDF
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
from requests.exceptions import RequestException

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

# Load environment variables from .env file
load_dotenv()

# Get the secret from environment variables
SECRET = os.getenv("SECRET")

# FastAPI application
app = FastAPI()


# Pydantic model for the incoming request
class QuizRequest(BaseModel):
    email: str
    secret: str
    url: str


async def solve_quiz(quiz_request: QuizRequest):
    """
    This function contains the logic to solve the quiz.
    It is executed in the background.
    """
    logging.info(f"Received quiz request for URL: {quiz_request.url}")
    
    browser = None
    try:
        async with async_playwright() as p:
            # --- Browser and Page Navigation ---
            try:
                browser = await p.chromium.launch()
                page = await browser.new_page()
                await page.goto(quiz_request.url, timeout=30000)
                logging.info(f"Successfully navigated to {quiz_request.url}")
            except Exception as e:
                logging.error(f"Failed to navigate to URL {quiz_request.url}. Error: {e}")
                return

            # --- Content Extraction and Parsing ---
            try:
                script_content = await page.evaluate(
                    'document.querySelector("#result + script").innerHTML'
                )
                base64_content = script_content.split('`')[1]
                decoded_content = base64.b64decode(base64_content).decode('utf-8')
                logging.info("Successfully extracted and decoded base64 content from script tag.")
            except Exception:
                logging.warning("Could not find or parse the script tag with base64 content. Falling back to full page content.")
                decoded_content = await page.content()

            soup = BeautifulSoup(decoded_content, 'lxml')
            question_text = soup.get_text()
            logging.info(f"Question Text: {question_text.strip()}")

            # --- Quiz Detail Extraction ---
            download_link = None
            submission_url = None
            try:
                if soup.find('a'):
                    download_link = soup.find('a')['href']
                    logging.info(f"Found download link: {download_link}")

                urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', question_text)
                for url in urls:
                    if "submit" in url:
                        submission_url = url
                        logging.info(f"Found submission URL: {submission_url}")
                        break
                
                if not submission_url:
                    logging.warning("Could not find a submission URL in the question text.")
                    return

            except Exception as e:
                logging.error(f"Error extracting quiz details (download or submission link). Error: {e}")
                return

            # --- Quiz Solving Logic ---
            answer = None
            if "sum of the “value” column" in question_text and download_link:
                try:
                    logging.info("Attempting to solve the PDF sum quiz...")
                    pdf_response = requests.get(download_link)
                    pdf_response.raise_for_status()
                    
                    # Use a temporary in-memory file for the PDF
                    pdf_document = fitz.open(stream=pdf_response.content, filetype="pdf")
                    logging.info("Successfully downloaded and opened the PDF file.")

                    if len(pdf_document) < 2:
                        logging.error("PDF has fewer than 2 pages, cannot find table on page 2.")
                        return
                        
                    page_two = pdf_document[1]
                    tables = page_two.find_tables()
                    
                    if tables:
                        # Assuming the first table on the page is the one we want
                        table_data = tables[0].extract()
                        header = table_data[0]
                        rows = table_data[1:]
                        
                        try:
                            value_index = header.index("value")
                        except ValueError:
                            logging.error("Could not find 'value' column in the table header.")
                            return

                        total_sum = 0
                        for row in rows:
                            try:
                                total_sum += float(row[value_index])
                            except (ValueError, TypeError):
                                # Ignore rows where the value is not a valid number
                                continue
                        
                        answer = total_sum
                        logging.info(f"Successfully processed PDF. Calculated sum: {answer}")
                    else:
                        logging.warning("Could not find any tables on page 2 of the PDF.")
                        return

                except RequestException as e:
                    logging.error(f"Failed to download PDF file. Error: {e}")
                    return
                except Exception as e: # General exception for fitz or other processing errors
                    logging.error(f"Failed to open or process PDF file. Error: {e}")
                    return

            else:
                logging.warning("Quiz type not recognized or required information is missing. Cannot solve.")
                return

            # --- Answer Submission ---
            if answer is not None:
                submission_payload = {
                    "email": quiz_request.email,
                    "secret": quiz_request.secret,
                    "url": quiz_request.url,
                    "answer": answer
                }
                try:
                    logging.info(f"Submitting answer: {submission_payload}")
                    submission_response = requests.post(submission_url, json=submission_payload, timeout=30)
                    submission_response.raise_for_status()
                    
                    response_json = submission_response.json()
                    logging.info(f"Submission response: {response_json}")

                    if response_json.get("correct"):
                        logging.info("Answer is correct!")
                        if "url" in response_json and response_json["url"]:
                            logging.info(f"New quiz URL found: {response_json['url']}")
                            new_quiz_request = QuizRequest(
                                email=quiz_request.email,
                                secret=quiz_request.secret,
                                url=response_json["url"]
                            )
                            # Schedule the next quiz without waiting for it to finish
                            background_tasks = BackgroundTasks()
                            background_tasks.add_task(solve_quiz, new_quiz_request)
                        else:
                            logging.info("Quiz series finished successfully!")
                    else:
                        reason = response_json.get('reason', 'No reason provided.')
                        logging.warning(f"Answer is incorrect. Reason: {reason}")

                except RequestException as e:
                    logging.error(f"Failed to submit answer to {submission_url}. Error: {e}")
                except json.JSONDecodeError:
                    logging.error("Failed to decode JSON from submission response.")
            
    except Exception as e:
        logging.critical(f"An unexpected error occurred in the main quiz solving process: {e}", exc_info=True)
    finally:
        if browser:
            await browser.close()
            logging.info("Browser closed.")


@app.post("/quiz")
async def receive_quiz(quiz_request: QuizRequest, background_tasks: BackgroundTasks):
    """
    API endpoint to receive quiz POST requests.
    """
    if quiz_request.secret != SECRET:
        logging.warning(f"Invalid secret received from email: {quiz_request.email}")
        raise HTTPException(status_code=403, detail="Invalid secret")

    background_tasks.add_task(solve_quiz, quiz_request)
    logging.info(f"Quiz request for {quiz_request.email} added to background tasks.")
    
    return {"message": "Quiz received and is being processed."}


@app.get("/")
def read_root():
    return {"message": "The quiz API is running. Send a POST request to /quiz to start."}