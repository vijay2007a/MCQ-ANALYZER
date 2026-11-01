import io
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from app.models.quiz import Quiz
from app.models.result import QuizResult
from app.models.question import Question
from app.models.answer import QuizAttempt


class ExportService:
    @staticmethod
    def generate_quiz_results_excel(db: Session, quiz_id: Optional[int] = None) -> io.BytesIO:
        wb = openpyxl.Workbook()
        
        # Color palette and typography styles
        header_fill = PatternFill(start_color="1E3A8A", end_color="1E3A8A", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        section_font = Font(name="Calibri", size=14, bold=True, color="1E3A8A")
        label_font = Font(name="Calibri", size=11, bold=True, color="334155")
        data_font = Font(name="Calibri", size=11, color="0F172A")
        thin_side = Side(border_style="thin", color="E2E8F0")
        cell_border = Border(top=thin_side, bottom=thin_side, left=thin_side, right=thin_side)

        # ----------------------------------------------------
        # SHEET 1: Summary KPI Sheet
        # ----------------------------------------------------
        ws_summary = wb.active
        ws_summary.title = "Summary"
        ws_summary.views.sheetView[0].showGridLines = True

        quiz_title = "All Quizzes"
        if quiz_id:
            quiz = db.query(Quiz).filter(Quiz.id == quiz_id).first()
            if quiz:
                quiz_title = quiz.title

        results_query = db.query(QuizResult)
        if quiz_id:
            results_query = results_query.filter(QuizResult.quiz_id == quiz_id)
        
        all_results = results_query.all()
        total_attempts = len(all_results)
        unique_participants = len(set(r.player_name.lower() for r in all_results))
        avg_score = round(sum(r.total_score for r in all_results) / total_attempts, 2) if total_attempts > 0 else 0.0
        avg_accuracy = round(sum(r.accuracy for r in all_results) / total_attempts, 2) if total_attempts > 0 else 0.0
        avg_time_ms = int(sum(r.total_time_ms for r in all_results) / total_attempts) if total_attempts > 0 else 0
        avg_time_sec = round(avg_time_ms / 1000.0, 1)

        ws_summary.merge_cells("A1:D1")
        ws_summary["A1"] = f"SBK Quiz Analyzer — Performance Summary ({quiz_title})"
        ws_summary["A1"].font = section_font
        ws_summary["A1"].alignment = Alignment(vertical="center")

        ws_summary["A2"] = f"Generated on: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
        ws_summary["A2"].font = Font(name="Calibri", size=10, italic=True, color="64748B")

        summary_metrics = [
            ("Quiz Scope", quiz_title),
            ("Total Attempts", total_attempts),
            ("Unique Participants", unique_participants),
            ("Average Score", avg_score),
            ("Average Accuracy (%)", f"{avg_accuracy}%"),
            ("Average Completion Time", f"{avg_time_sec} s"),
        ]

        row_idx = 4
        for label, val in summary_metrics:
            ws_summary[f"A{row_idx}"] = label
            ws_summary[f"A{row_idx}"].font = label_font
            ws_summary[f"A{row_idx}"].fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")
            ws_summary[f"A{row_idx}"].border = cell_border
            
            ws_summary[f"B{row_idx}"] = val
            ws_summary[f"B{row_idx}"].font = data_font
            ws_summary[f"B{row_idx}"].border = cell_border
            ws_summary[f"B{row_idx}"].alignment = Alignment(horizontal="left" if isinstance(val, str) else "right")
            row_idx += 1

        # ----------------------------------------------------
        # SHEET 2: Results Data Sheet
        # ----------------------------------------------------
        ws_results = wb.create_sheet(title="Results")
        ws_results.views.sheetView[0].showGridLines = True

        results_headers = [
            "Rank",
            "Student Name",
            "Register Number",
            "Quiz Name",
            "Total Questions",
            "Correct Answers",
            "Wrong Answers",
            "Unanswered Questions",
            "Marks Obtained",
            "Percentage",
            "Completion Time",
            "Submission Time",
            "Quiz Status",
            "Recorded Warnings",
            "Player Name",
            "Score",
            "Accuracy (%)",
        ]

        ws_results.append(results_headers)
        for col_num in range(1, len(results_headers) + 1):
            cell = ws_results.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = cell_border

        # Deterministic ranking query
        sorted_results = (
            results_query.order_by(
                QuizResult.total_score.desc(),
                QuizResult.total_time_ms.asc(),
                QuizResult.completed_at.asc(),
            ).all()
        )

        last_key = None
        current_rank = 1
        for idx, r in enumerate(sorted_results, start=1):
            key = (r.total_score, r.total_time_ms)
            if last_key is not None and key == last_key:
                rank = current_rank
            else:
                rank = idx
                current_rank = idx
            last_key = key

            unans = getattr(r, "unanswered_questions", 0) or 0
            wrong_only = max(0, r.incorrect_answers - unans)
            marks_obt = getattr(r, "marks_obtained", r.correct_answers)
            if marks_obt is None or (marks_obt == 0 and r.correct_answers > 0):
                marks_obt = r.correct_answers
            warnings_cnt = getattr(r, "warnings_count", 0) or 0
            if warnings_cnt == 0 and r.session:
                warnings_cnt = getattr(r.session, "warnings_count", 0) or 0
            q_status = getattr(r, "quiz_status", None) or (r.session.status if r.session else "COMPLETED")

            row_data = [
                rank,
                r.player_name,
                getattr(r, "register_number", None) or (r.session.register_number if r.session else "-") or "-",
                r.quiz.title if r.quiz else f"Quiz #{r.quiz_id}",
                r.total_questions,
                r.correct_answers,
                wrong_only,
                unans,
                marks_obt,
                r.accuracy,
                f"{round(r.total_time_ms / 1000.0, 2)}s",
                r.completed_at.strftime("%Y-%m-%d %H:%M:%S") if r.completed_at else "",
                q_status,
                warnings_cnt,
                r.player_name,
                r.total_score,
                r.accuracy,
            ]
            ws_results.append(row_data)
            current_row = ws_results.max_row
            for col_idx in range(1, len(row_data) + 1):
                c = ws_results.cell(row=current_row, column=col_idx)
                c.font = data_font
                c.border = cell_border
                if col_idx in [1, 5, 6, 7, 8, 9, 10, 14, 16, 17]:
                    c.alignment = Alignment(horizontal="right")
                else:
                    c.alignment = Alignment(horizontal="left")

        ws_results.freeze_panes = "A2"
        if sorted_results:
            ws_results.auto_filter.ref = ws_results.dimensions

        # ----------------------------------------------------
        # SHEET 3: Question Performance Sheet
        # ----------------------------------------------------
        ws_questions = wb.create_sheet(title="Question Performance")
        ws_questions.views.sheetView[0].showGridLines = True

        q_headers = [
            "Question #",
            "Question Text",
            "Total Answers",
            "Correct Answers",
            "Incorrect Answers",
            "Correct Percentage (%)",
            "Avg Response Time (ms)",
        ]

        ws_questions.append(q_headers)
        for col_num in range(1, len(q_headers) + 1):
            cell = ws_questions.cell(row=1, column=col_num)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = cell_border

        # Fetch questions based on filter
        q_query = db.query(Question)
        if quiz_id:
            q_query = q_query.filter(Question.quiz_id == quiz_id)
        
        questions = q_query.order_by(Question.quiz_id.asc(), Question.question_order.asc()).all()

        for q in questions:
            attempts = db.query(QuizAttempt).filter(QuizAttempt.question_id == q.id).all()
            q_total_ans = len(attempts)
            q_correct_ans = sum(1 for a in attempts if a.is_correct)
            q_incorrect_ans = q_total_ans - q_correct_ans
            q_pct_correct = round((q_correct_ans / q_total_ans * 100.0), 2) if q_total_ans > 0 else 0.0
            q_avg_resp_ms = int(sum(a.response_time_ms for a in attempts) / q_total_ans) if q_total_ans > 0 else 0

            row_data = [
                q.question_order,
                q.question_text,
                q_total_ans,
                q_correct_ans,
                q_incorrect_ans,
                q_pct_correct,
                q_avg_resp_ms,
            ]
            ws_questions.append(row_data)
            current_row = ws_questions.max_row
            for col_idx in range(1, len(row_data) + 1):
                c = ws_questions.cell(row=current_row, column=col_idx)
                c.font = data_font
                c.border = cell_border
                if col_idx in [1, 3, 4, 5, 6, 7]:
                    c.alignment = Alignment(horizontal="right")
                else:
                    c.alignment = Alignment(horizontal="left")

        ws_questions.freeze_panes = "A2"
        if questions:
            ws_questions.auto_filter.ref = ws_questions.dimensions

        # ----------------------------------------------------
        # Auto-fit Column Widths across all sheets
        # ----------------------------------------------------
        for ws in [ws_summary, ws_results, ws_questions]:
            for col in ws.columns:
                max_len = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    val_str = str(cell.value or "")
                    if cell.number_format and "%" in cell.number_format:
                        val_str += "%"
                    if len(val_str) > max_len:
                        max_len = len(val_str)
                # Bound width between 12 and 60
                ws.column_dimensions[col_letter].width = max(12, min(max_len + 4, 60))

        output_stream = io.BytesIO()
        wb.save(output_stream)
        output_stream.seek(0)
        return output_stream


export_service = ExportService()
