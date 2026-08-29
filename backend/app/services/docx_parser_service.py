import io
import re
from typing import List, Dict, Any, Optional
import docx


class DocxParserService:
    """
    Deterministic parser for Word (.docx) assessment files containing MCQs.
    Extracts Quiz Title, Questions (Q1, Q2...), Options (A, B, C, D), Correct Answer, and Explanations.
    Surfaces explicit validation errors for malformed questions without silent corruption.
    """

    # Regex patterns for line matching
    QUIZ_TITLE_PATTERN = re.compile(r"^(?:QUIZ\s*TITLE|TITLE|QUIZ\s*NAME)\s*[:\-]\s*(.+)$", re.IGNORECASE)
    QUESTION_START_PATTERN = re.compile(r"^(?:Q\s*(\d+)[\.:\)\-]|Question\s*(\d+)[\.:\)\-]|(\d+)[\.:\)])\s*(.*)$", re.IGNORECASE)
    OPTION_PATTERN = re.compile(r"^([A-D])[\.:\)\-]\s*(.*)$", re.IGNORECASE)
    ANSWER_PATTERN = re.compile(r"^(?:ANSWER|ANS|CORRECT\s*ANSWER|CORRECT)\s*[:\-]\s*([A-D])", re.IGNORECASE)
    EXPLANATION_PATTERN = re.compile(r"^(?:EXPLANATION|EXPLAIN|REASON|EXP)\s*[:\-]\s*(.*)$", re.IGNORECASE)

    def parse_docx_bytes(self, file_bytes: bytes, fallback_title: str = "Imported Quiz") -> Dict[str, Any]:
        """
        Parses a .docx file provided as raw bytes.
        """
        try:
            doc = docx.Document(io.BytesIO(file_bytes))
        except Exception as e:
            return {
                "quiz_title": fallback_title,
                "total_parsed": 0,
                "valid_questions_count": 0,
                "errors": [f"Unable to read Word document (.docx): {str(e)}"],
                "questions": [],
                "is_valid": False,
            }

        lines: List[str] = []
        for p in doc.paragraphs:
            text = p.text.strip()
            if text:
                lines.append(text)

        # Also check tables in case MCQs or questions were stored in table cells
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    text = cell.text.strip()
                    if text and text not in lines:
                        for sub_line in text.split("\n"):
                            sub_line = sub_line.strip()
                            if sub_line and sub_line not in lines:
                                lines.append(sub_line)

        return self.parse_text_lines(lines, fallback_title=fallback_title)

    def parse_text_lines(self, lines: List[str], fallback_title: str = "Imported Quiz") -> Dict[str, Any]:
        """
        Parses structured text lines into quiz metadata and question objects with strict validation.
        """
        quiz_title = fallback_title
        raw_question_blocks: List[List[str]] = []
        current_block: List[str] = []
        title_found = False

        for line in lines:
            # Check for QUIZ TITLE on early lines
            if not title_found:
                title_match = self.QUIZ_TITLE_PATTERN.match(line)
                if title_match:
                    quiz_title = title_match.group(1).strip()
                    title_found = True
                    continue

            # Check for question start: Q1., Q2., Question 1:, 1. etc.
            q_match = self.QUESTION_START_PATTERN.match(line)
            if q_match:
                if current_block:
                    raw_question_blocks.append(current_block)
                current_block = [line]
            else:
                if current_block:
                    current_block.append(line)

        if current_block:
            raw_question_blocks.append(current_block)

        # Process and validate each raw question block
        parsed_questions: List[Dict[str, Any]] = []
        global_errors: List[str] = []

        if not raw_question_blocks:
            global_errors.append("No questions found in document. Please ensure questions start with 'Q1.', 'Q2.', 'Question 1:', etc.")

        for idx, block in enumerate(raw_question_blocks, start=1):
            q_data, q_errors = self._process_question_block(block, expected_index=idx)
            parsed_questions.append(q_data)
            if q_errors:
                global_errors.extend(q_errors)

        valid_count = sum(1 for q in parsed_questions if q["is_valid"])

        return {
            "quiz_title": quiz_title,
            "total_parsed": len(parsed_questions),
            "valid_questions_count": valid_count,
            "errors": global_errors,
            "questions": parsed_questions,
            "is_valid": len(global_errors) == 0 and len(parsed_questions) > 0,
        }

    def _process_question_block(self, block: List[str], expected_index: int) -> tuple[Dict[str, Any], List[str]]:
        """
        Parses an individual question block and applies strict validation.
        """
        errors: List[str] = []
        question_num = expected_index

        question_text_parts: List[str] = []
        options: Dict[str, str] = {}
        correct_answer: Optional[str] = None
        explanation_parts: List[str] = []

        current_mode = "QUESTION"
        current_option = None

        for line in block:
            # Check question start
            q_match = self.QUESTION_START_PATTERN.match(line)
            if q_match and not question_text_parts:
                extracted_num = q_match.group(1) or q_match.group(2) or q_match.group(3)
                if extracted_num:
                    try:
                        question_num = int(extracted_num)
                    except ValueError:
                        pass
                initial_text = q_match.group(4).strip()
                if initial_text:
                    question_text_parts.append(initial_text)
                current_mode = "QUESTION"
                continue

            # Check Option: A., B., C., D.
            opt_match = self.OPTION_PATTERN.match(line)
            if opt_match:
                opt_letter = opt_match.group(1).upper()
                opt_val = opt_match.group(2).strip()
                options[opt_letter] = opt_val
                current_option = opt_letter
                current_mode = "OPTION"
                continue

            # Check Answer: ANSWER: A
            ans_match = self.ANSWER_PATTERN.match(line)
            if ans_match:
                correct_answer = ans_match.group(1).upper()
                current_mode = "ANSWER"
                continue

            # Check if line contains "ANSWER:" but with invalid value
            if re.match(r"^(?:ANSWER|ANS|CORRECT\s*ANSWER|CORRECT)\s*[:\-]", line, re.IGNORECASE):
                val = re.sub(r"^(?:ANSWER|ANS|CORRECT\s*ANSWER|CORRECT)\s*[:\-]\s*", "", line, flags=re.IGNORECASE).strip()
                if val.upper() in ["A", "B", "C", "D"]:
                    correct_answer = val.upper()
                else:
                    errors.append(f"Question {question_num}: Invalid ANSWER value '{val}'. Must be A, B, C, or D.")
                    correct_answer = None
                current_mode = "ANSWER"
                continue

            # Check Explanation
            exp_match = self.EXPLANATION_PATTERN.match(line)
            if exp_match:
                exp_text = exp_match.group(1).strip()
                if exp_text:
                    explanation_parts.append(exp_text)
                current_mode = "EXPLANATION"
                continue

            # Multi-line continuation handling based on current mode
            if current_mode == "QUESTION":
                question_text_parts.append(line)
            elif current_mode == "OPTION" and current_option:
                options[current_option] = (options[current_option] + " " + line).strip()
            elif current_mode == "EXPLANATION":
                explanation_parts.append(line)

        # Assemble extracted fields
        question_text = " ".join(question_text_parts).strip()
        explanation = " ".join(explanation_parts).strip()

        # Strict Validations
        if not question_text:
            errors.append(f"Question {question_num}: Missing question text.")
        elif len(question_text) < 5:
            errors.append(f"Question {question_num}: Question text too short (minimum 5 characters).")

        # Validate exactly 4 options
        for opt in ["A", "B", "C", "D"]:
            if opt not in options or not options[opt].strip():
                errors.append(f"Question {question_num}: Missing option {opt}.")

        # Validate Answer
        if not correct_answer:
            if not any(f"Question {question_num}: Invalid ANSWER" in e for e in errors):
                errors.append(f"Question {question_num}: Missing ANSWER definition (e.g. ANSWER: B).")

        # Fallback explanation if empty
        if not explanation:
            explanation = f"Correct answer is option {correct_answer or 'A'}."

        q_dict = {
            "question_order": question_num,
            "question_text": question_text,
            "option_a": options.get("A", ""),
            "option_b": options.get("B", ""),
            "option_c": options.get("C", ""),
            "option_d": options.get("D", ""),
            "correct_option": correct_answer or "A",
            "explanation": explanation,
            "is_valid": len(errors) == 0,
            "validation_errors": errors,
        }

        return q_dict, errors


docx_parser_service = DocxParserService()
