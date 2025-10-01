from django.db import models
from django.contrib.auth.models import User
from questions.question_models import Question_DB
from questions.questionpaper_models import Question_Paper

class StudentInfo(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, db_index=True)
    address = models.CharField(max_length=200, blank=True)
    stream = models.CharField(max_length=50, blank=True, db_index=True)
    picture = models.ImageField(upload_to='student_profile_pics', blank=True)
    # created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.user.username
    
    class Meta:
        verbose_name_plural = 'Student Info'
        indexes = [
            models.Index(fields=['user', 'stream']),
            # models.Index(fields=['created_at']),
        ]

class Stu_Question(Question_DB):
    professor = None
    student = models.ForeignKey(User, limit_choices_to={'groups__name': "Student"}, on_delete=models.CASCADE, null=True, db_index=True)
    choice = models.CharField(max_length=3, default="E", db_index=True)
    answered_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return str(self.student.username) + " "+ str(self.qno) +"-Stu_QuestionDB"
    
    class Meta:
        indexes = [
            models.Index(fields=['student', 'choice']),
            models.Index(fields=['answered_at']),
        ]


class StuExam_DB(models.Model):
    student = models.ForeignKey(User, limit_choices_to={'groups__name': "Student"}, on_delete=models.CASCADE, null=True, db_index=True)
    examname = models.CharField(max_length=100, db_index=True)
    qpaper = models.ForeignKey(Question_Paper, on_delete=models.CASCADE, null=True, db_index=True)
    questions = models.ManyToManyField(Stu_Question)
    score = models.IntegerField(default=0, db_index=True)
    completed = models.IntegerField(default=0, db_index=True)
    # created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.student.username) +" " + str(self.examname) + " " + str(self.qpaper.qPaperTitle) + "-StuExam_DB"
    
    class Meta:
        indexes = [
            models.Index(fields=['student', 'examname']),
            models.Index(fields=['student', 'score']),
            models.Index(fields=['examname', 'completed']),
            # models.Index(fields=['created_at']),
        ]


class StuResults_DB(models.Model):
    student = models.ForeignKey(User, limit_choices_to={'groups__name': "Student"}, on_delete=models.CASCADE, null=True, db_index=True)
    exams = models.ManyToManyField(StuExam_DB)
    # created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    # updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return str(self.student.username) +" -StuResults_DB"
    
    class Meta:
        indexes = [
            # models.Index(fields=['student', 'created_at']),
        ]