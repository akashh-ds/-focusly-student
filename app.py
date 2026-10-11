import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-before-deploying")
database_url = os.environ.get("DATABASE_URL", "sqlite:///focusly.db")
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    subject = db.Column(db.String(100), default="General")
    kind = db.Column(db.String(30), default="Assignment")
    priority = db.Column(db.String(20), default="Medium")
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="Pending")
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    exam_name = db.Column(db.String(160), nullable=False)
    exam_date = db.Column(db.Date, nullable=False)
    syllabus_total = db.Column(db.Integer, default=0)
    syllabus_done = db.Column(db.Integer, default=0)

with app.app_context():
    db.create_all()

@app.template_filter("prettydate")
def prettydate(value):
    return value.strftime("%d %b %Y") if value else "No deadline"

@app.context_processor
def inject_globals():
    today = date.today()
    all_tasks = Task.query.all()
    return {
        "today": today,
        "nav_counts": {
            "all": len(all_tasks),
            "pending": sum(1 for t in all_tasks if t.status != "Completed"),
            "completed": sum(1 for t in all_tasks if t.status == "Completed"),
        }
    }

@app.route("/")
def dashboard():
    tasks = Task.query.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()).all()
    upcoming = [t for t in tasks if t.status != "Completed" and t.due_date and t.due_date >= date.today()][:4]
    exams = Exam.query.order_by(Exam.exam_date.asc()).all()
    pending = [t for t in tasks if t.status != "Completed"]
    completed = [t for t in tasks if t.status == "Completed"]
    overdue = [t for t in pending if t.due_date and t.due_date < date.today()]
    return render_template("dashboard.html", tasks=tasks[:6], upcoming=upcoming, exams=exams[:3],
                           pending_count=len(pending), completed_count=len(completed),
                           overdue_count=len(overdue), total_count=len(tasks))

@app.route("/tasks")
def tasks_page():
    status = request.args.get("status", "All")
    kind = request.args.get("kind", "All")
    query = Task.query
    if status in ("Pending", "In progress", "Completed"):
        query = query.filter_by(status=status)
    if kind in ("Assignment", "Practical", "Study", "Other"):
        query = query.filter_by(kind=kind)
    tasks = query.order_by(Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()).all()
    return render_template("tasks.html", tasks=tasks, active_status=status, active_kind=kind)

@app.route("/tasks/add", methods=["POST"])
def add_task():
    title = request.form.get("title", "").strip()
    if not title:
        flash("Add a task title first.", "error")
        return redirect(request.referrer or url_for("tasks_page"))
    raw_due = request.form.get("due_date", "").strip()
    due = date.fromisoformat(raw_due) if raw_due else None
    task = Task(title=title, subject=request.form.get("subject", "General").strip() or "General",
                kind=request.form.get("kind", "Assignment"), priority=request.form.get("priority", "Medium"),
                due_date=due, notes=request.form.get("notes", "").strip())
    db.session.add(task)
    db.session.commit()
    flash("Task added to your plan.", "success")
    return redirect(request.referrer or url_for("tasks_page"))

@app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
def toggle_task(task_id):
    task = db.get_or_404(Task, task_id)
    task.status = "Completed" if task.status != "Completed" else "Pending"
    db.session.commit()
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"ok": True, "status": task.status})
    flash("Task updated.", "success")
    return redirect(request.referrer or url_for("tasks_page"))

@app.route("/tasks/<int:task_id>/status", methods=["POST"])
def update_status(task_id):
    task = db.get_or_404(Task, task_id)
    status = request.form.get("status", "Pending")
    if status in ("Pending", "In progress", "Completed"):
        task.status = status
        db.session.commit()
        flash("Task status updated.", "success")
    return redirect(request.referrer or url_for("tasks_page"))

@app.route("/tasks/<int:task_id>/delete", methods=["POST"])
def delete_task(task_id):
    task = db.get_or_404(Task, task_id)
    db.session.delete(task)
    db.session.commit()
    flash("Task deleted.", "success")
    return redirect(request.referrer or url_for("tasks_page"))

@app.route("/exams")
def exams_page():
    exams = Exam.query.order_by(Exam.exam_date.asc()).all()
    return render_template("exams.html", exams=exams)

@app.route("/exams/add", methods=["POST"])
def add_exam():
    subject = request.form.get("subject", "").strip()
    name = request.form.get("exam_name", "").strip()
    raw_date = request.form.get("exam_date", "").strip()
    if not subject or not name or not raw_date:
        flash("Please complete the subject, exam name, and date.", "error")
        return redirect(url_for("exams_page"))
    total = max(0, int(request.form.get("syllabus_total", 0) or 0))
    done = max(0, int(request.form.get("syllabus_done", 0) or 0))
    db.session.add(Exam(subject=subject, exam_name=name, exam_date=date.fromisoformat(raw_date),
                        syllabus_total=total, syllabus_done=min(done, total) if total else done))
    db.session.commit()
    flash("Exam added.", "success")
    return redirect(url_for("exams_page"))

@app.route("/exams/<int:exam_id>/delete", methods=["POST"])
def delete_exam(exam_id):
    exam = db.get_or_404(Exam, exam_id)
    db.session.delete(exam)
    db.session.commit()
    flash("Exam removed.", "success")
    return redirect(url_for("exams_page"))

@app.route("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    app.run(debug=True)
