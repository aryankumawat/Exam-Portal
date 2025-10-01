"""
API URL configuration
"""
from django.urls import path
from . import views

urlpatterns = [
    # Student API endpoints
    path('student/<str:endpoint>/', views.StudentAPIView.as_view(), name='student_api'),
    
    # Faculty API endpoints
    path('faculty/<str:endpoint>/', views.FacultyAPIView.as_view(), name='faculty_api'),
]
