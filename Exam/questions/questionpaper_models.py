from django.db import models
from django.forms import ModelForm
from django.contrib.auth.models import User
from .question_models import Question_DB
from django import forms

class Question_Paper(models.Model):
    professor = models.ForeignKey(User, limit_choices_to={'groups__name': "Professor"}, on_delete=models.CASCADE, db_index=True)
    qPaperTitle = models.CharField(max_length=100, db_index=True)
    questions = models.ManyToManyField(Question_DB)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f' Question Paper Title :- {self.qPaperTitle}\n'
    
    class Meta:
        indexes = [
            models.Index(fields=['professor', 'is_active']),
            models.Index(fields=['professor', 'created_at']),
            models.Index(fields=['qPaperTitle']),
            models.Index(fields=['created_at']),
        ]


class QPForm(ModelForm):
    def __init__(self,professor,*args,**kwargs):
        super (QPForm,self ).__init__(*args,**kwargs) 
        self.fields['questions'].queryset = Question_DB.objects.filter(professor=professor)

    class Meta:
        model = Question_Paper
        fields = '__all__'
        exclude = ['professor']
        widgets = {
            'qPaperTitle': forms.TextInput(attrs = {'class':'form-control'})
        }
