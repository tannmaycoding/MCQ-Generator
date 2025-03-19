import json
import re
import streamlit as st
from langchain_core.prompts import ChatPromptTemplate
from langchain_huggingface import HuggingFaceEndpoint

st.title("Quiz App")


def fix_value_strings(s):
    result = ""
    i = 0
    while i < len(s):
        if s[i:i + 2] == ": " and i + 2 < len(s) and s[i + 2] == "'":
            result += ": "
            i += 2
            result += '"'
            i += 1
            value_chars = []
            while i < len(s):
                if s[i] == "'":
                    j = i + 1
                    while j < len(s) and s[j].isspace():
                        j += 1
                    if j < len(s) and s[j] in [',', '}']:
                        break
                    else:
                        value_chars.append('\\"')
                        i += 1
                        continue
                else:
                    value_chars.append(s[i])
                    i += 1
            result += ''.join(value_chars) + '"'
            i += 1
        else:
            result += s[i]
            i += 1
    return result


def process_chain_response(response):
    first_brace = response.find("{")
    if first_brace != -1:
        response = response[first_brace:]
    blocks = re.split(r"(?=\{'(?:\d+)':)", response)
    valid_blocks = {}
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        if block.endswith(","):
            block = block[:-1]
        fixed_block = re.sub(r"'(\w+)'(?=\s*:)", r'"\1"', block)
        fixed_block = fix_value_strings(fixed_block)
        try:
            d = json.loads(fixed_block)
            valid_blocks.update(d)
        except Exception:
            continue
    return valid_blocks


def fix_and_convert_to_json(input_str):
    try:
        input_str = input_str.strip()
        merged = process_chain_response(input_str)
        return merged
    except Exception as e:
        st.error(f"Error converting input: {e}")
        return None


# Initialize session state variables if not set.
if "mode" not in st.session_state:
    st.session_state.mode = "login"
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = {}
if "score" not in st.session_state:
    st.session_state.score = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "results" not in st.session_state:
    st.session_state.results = []

# Login screen
if st.session_state.mode == "login":
    access = st.text_input("Enter your Hugging Face access token: ")
    if st.button("Continue", key="continue"):
        st.session_state.access = access
        st.session_state.mode = "make"
        st.rerun()

# Quiz creation screen ("make" mode)
if st.session_state.mode == "make":
    llm = HuggingFaceEndpoint(
        repo_id="mistralai/Mistral-7B-Instruct-v0.3",
        max_length=128,
        temperature=0.8,
        huggingfacehub_api_token=st.session_state.access
    )
    prompt = (
        "You are a teacher who wants to make tests for your students consisting of MCQs. "
        "You have to make questions on {subject}. The difficulty of questions would be {difficulty}. "
        "You have to respond in the following format: {json}. There should not be any extra words. "
        "You must follow the format exactly. Just fill the parameters of the JSON data given. "
        "Make sure that the brackets are correctly closed. Nothing other than the JSON should be returned. "
        "Remember this"
    )
    st.session_state.json_data = {
        "1": {
            "question": "This will be the question",
            "options": {
                "A": "This is the first option",
                "B": "This is the second option",
                "C": "This is the third option",
                "D": "This is the fourth option"
            },
            "correct": "Which option is correct. Just write the letter",
            "reason": "Why this is the correct option"
        }
    }
    template = ChatPromptTemplate.from_template(prompt)
    st.session_state.chain = template | llm

    st.session_state.subject = st.text_input("What is the subject: ")
    st.session_state.difficulty = st.selectbox("What should be the difficulty: ", ["easy", "intermediate", "hard"])

    if st.button("Make Quiz", key="make_quiz"):
        st.session_state.mode = "quiz"
        st.rerun()

if st.session_state.mode == "quiz":
    # Only generate the quiz once
    if not st.session_state.quiz_data:
        response = st.session_state.chain.invoke({
            "number": 5,
            "subject": st.session_state.subject,
            "difficulty": st.session_state.difficulty,
            "json": st.session_state.json_data
        })
        quiz = fix_and_convert_to_json(response)
        if quiz and isinstance(quiz, dict):
            st.session_state.quiz_data = quiz
            st.session_state.score = 0
            st.session_state.answers = {}
        else:
            st.error("Failed to generate quiz. Please try again.")

    # Display the quiz questions
    if st.session_state.quiz_data:
        for q_id, q_data in st.session_state.quiz_data.items():
            st.markdown(f"**{q_id}. {q_data['question']}**")
            if q_id not in st.session_state.answers:
                st.session_state.answers[q_id] = None
            st.session_state.answers[q_id] = st.radio(
                "Select the correct answer",
                options=list(q_data['options'].values()),
                key=f"q_{q_id}",
                index=(list(q_data['options'].values()).index(st.session_state.answers[q_id])
                       if st.session_state.answers[q_id] in q_data["options"].values() else 0)
            )

        # If quiz is not submitted yet
        if "submitted" not in st.session_state:
            st.session_state.submitted = False

        if not st.session_state.submitted:
            if st.button("Submit", key="submit"):
                st.session_state.score = 0
                st.session_state.results = []
                for q_id, q_data in st.session_state.quiz_data.items():
                    selected = st.session_state.answers[q_id]
                    correct = q_data["options"].get(q_data["correct"], None)
                    if selected == correct:
                        st.session_state.score += 1
                        st.session_state.results.append(f"✅ **Question {q_id}:** Correct! {q_data['reason']}")
                    else:
                        st.session_state.results.append(
                            f"❌ **Question {q_id}:** Incorrect. The correct answer is **{correct}**. {q_data['reason']}")

                # Set `submitted = True` before re-running
                st.session_state.submitted = True
                st.rerun()
        else:
            # Show results after submission
            st.markdown(f"### **Your Score: {st.session_state.score} / {len(st.session_state.quiz_data)}**")
            for res in st.session_state.results:
                st.markdown(res)

            # Show "Make New Quiz" button
            if st.button("Make New Quiz", key="new_quiz"):
                st.session_state.quiz_data = {}
                st.session_state.score = 0
                st.session_state.answers = {}
                st.session_state.mode = "make"
                st.session_state.submitted = False  # Reset for the next quiz
                st.session_state.results = []
                st.rerun()
