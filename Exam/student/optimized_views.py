"""
Optimized views with better database queries and performance improvements
"""
from django.shortcuts import render, redirect
from django.views import View
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Prefetch, Count, Avg, Q
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.cache import cache_page
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
import logging

from .models import StudentInfo, StuExam_DB, StuResults_DB, Stu_Question
from questions.question_models import Question_DB
from questions.questionpaper_models import Question_Paper

logger = logging.getLogger(__name__)

@method_decorator([csrf_protect, never_cache], name='dispatch')
class OptimizedStudentDashboard(View):
    """
    Optimized student dashboard with efficient database queries
    """
    
    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    def get(self, request):
        try:
            # Get student info with select_related to avoid N+1 queries
            student_info = StudentInfo.objects.select_related('user').get(user=request.user)
            
            # Optimized exam queries with prefetch_related
            student_exams = StuExam_DB.objects.filter(
                student=request.user
            ).select_related('qpaper', 'qpaper__professor').prefetch_related(
                'questions'
            ).order_by('-created_at')
            
            # Get exam statistics efficiently
            exam_stats = student_exams.aggregate(
                total_exams=Count('id'),
                completed_exams=Count('id', filter=Q(completed=1)),
                avg_score=Avg('score'),
                total_score=Count('score', filter=Q(score__gt=0))
            )
            
            # Get recent activity with optimized queries
            recent_activities = student_exams[:5]
            
            # Get upcoming exams (not completed)
            upcoming_exams = student_exams.filter(completed=0)[:3]
            
            # Get practice tests (sample data for now)
            practice_tests = [
                {
                    'name': 'Chemistry Practice Test',
                    'questions': 50,
                    'duration': 60,
                    'difficulty': 'Medium'
                },
                {
                    'name': 'Mathematics Quiz',
                    'questions': 30,
                    'duration': 45,
                    'difficulty': 'Easy'
                },
                {
                    'name': 'Physics Mock Exam',
                    'questions': 75,
                    'duration': 90,
                    'difficulty': 'Hard'
                }
            ]
            
            # Get announcements (sample data)
            announcements = [
                {
                    'title': 'Midterm Exam Schedule',
                    'content': 'All midterm exams will be conducted from March 15-20.',
                    'priority': 'high',
                    'date': '2 days ago'
                },
                {
                    'title': 'New Study Materials Available',
                    'content': 'Additional practice questions and video tutorials uploaded.',
                    'priority': 'medium',
                    'date': '1 week ago'
                }
            ]
            
            context = {
                'student_info': student_info,
                'exam_stats': exam_stats,
                'recent_activities': recent_activities,
                'upcoming_exams': upcoming_exams,
                'practice_tests': practice_tests,
                'announcements': announcements,
            }
            
            return render(request, 'student/index.html', context)
            
        except StudentInfo.DoesNotExist:
            logger.warning(f"StudentInfo not found for user {request.user.username}")
            messages.error(request, "Student profile not found. Please contact support.")
            return redirect('login')
        except Exception as e:
            logger.error(f"Error in OptimizedStudentDashboard: {e}")
            messages.error(request, "An error occurred while loading the dashboard.")
            return redirect('login')


@method_decorator([csrf_protect, never_cache], name='dispatch')
class OptimizedExamList(View):
    """
    Optimized exam list view with pagination and filtering
    """
    
    def get(self, request):
        try:
            # Get available exams with optimized queries
            exams = Question_Paper.objects.filter(
                is_active=True
            ).select_related('professor').prefetch_related(
                'questions'
            ).annotate(
                question_count=Count('questions'),
                total_marks=Count('questions__max_marks')
            ).order_by('-created_at')
            
            # Add pagination
            paginator = Paginator(exams, 12)  # 12 exams per page
            page_number = request.GET.get('page')
            page_obj = paginator.get_page(page_number)
            
            # Get student's exam history for comparison
            student_exams = StuExam_DB.objects.filter(
                student=request.user
            ).values_list('qpaper_id', flat=True)
            
            context = {
                'exams': page_obj,
                'student_exams': student_exams,
                'total_exams': paginator.count,
            }
            
            return render(request, 'exam/mainexamstudent.html', context)
            
        except Exception as e:
            logger.error(f"Error in OptimizedExamList: {e}")
            messages.error(request, "An error occurred while loading exams.")
            return redirect('student-index')


@method_decorator([csrf_protect, never_cache], name='dispatch')
class OptimizedResultsView(View):
    """
    Optimized results view with efficient data aggregation
    """
    
    def get(self, request):
        try:
            # Get student's exam results with optimized queries
            student_results = StuResults_DB.objects.filter(
                student=request.user
            ).prefetch_related(
                'exams__qpaper',
                'exams__questions'
            ).first()
            
            if not student_results:
                # Return empty results with sample data
                context = {
                    'students': {},
                    'has_results': False
                }
                return render(request, 'exam/resultsstudent.html', context)
            
            # Aggregate results efficiently
            exam_data = {}
            for exam in student_results.exams.all():
                exam_data[exam.examname] = {
                    'score': exam.score,
                    'completed': exam.completed,
                    'qpaper_title': exam.qpaper.qPaperTitle if exam.qpaper else 'N/A',
                    'created_at': exam.created_at
                }
            
            # Calculate performance statistics
            total_exams = len(exam_data)
            completed_exams = sum(1 for data in exam_data.values() if data['completed'])
            avg_score = sum(data['score'] for data in exam_data.values()) / total_exams if total_exams > 0 else 0
            
            context = {
                'students': exam_data,
                'has_results': True,
                'stats': {
                    'total_exams': total_exams,
                    'completed_exams': completed_exams,
                    'avg_score': round(avg_score, 2),
                    'success_rate': round((completed_exams / total_exams) * 100, 2) if total_exams > 0 else 0
                }
            }
            
            return render(request, 'exam/resultsstudent.html', context)
            
        except Exception as e:
            logger.error(f"Error in OptimizedResultsView: {e}")
            messages.error(request, "An error occurred while loading results.")
            return redirect('student-index')


class OptimizedAPIView(View):
    """
    Optimized API endpoints with better validation and error responses
    """
    
    def get(self, request, endpoint):
        try:
            if endpoint == 'stats':
                # Get student statistics efficiently
                student_exams = StuExam_DB.objects.filter(student=request.user)
                
                stats = {
                    'total_exams': student_exams.count(),
                    'completed_exams': student_exams.filter(completed=1).count(),
                    'avg_score': student_exams.aggregate(avg_score=Avg('score'))['avg_score'] or 0,
                    'total_questions': Stu_Question.objects.filter(student=request.user).count(),
                }
                
                return JsonResponse({
                    'success': True,
                    'data': stats
                })
                
            elif endpoint == 'recent_activity':
                # Get recent activity efficiently
                recent_exams = StuExam_DB.objects.filter(
                    student=request.user
                ).select_related('qpaper').order_by('-created_at')[:10]
                
                activities = []
                for exam in recent_exams:
                    activities.append({
                        'id': exam.id,
                        'exam_name': exam.examname,
                        'score': exam.score,
                        'completed': exam.completed,
                        'created_at': exam.created_at.isoformat(),
                        'qpaper_title': exam.qpaper.qPaperTitle if exam.qpaper else 'N/A'
                    })
                
                return JsonResponse({
                    'success': True,
                    'data': activities
                })
                
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid endpoint'
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error in OptimizedAPIView: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Internal server error'
            }, status=500)
    
    def post(self, request, endpoint):
        try:
            if endpoint == 'update_preferences':
                # Update student preferences efficiently
                data = request.json() if hasattr(request, 'json') else {}
                
                # Validate required fields
                required_fields = ['theme', 'notifications']
                if not all(field in data for field in required_fields):
                    return JsonResponse({
                        'success': False,
                        'error': 'Missing required fields'
                    }, status=400)
                
                # Update preferences (implement based on your preference model)
                # This is a placeholder - implement based on your actual preference model
                
                return JsonResponse({
                    'success': True,
                    'message': 'Preferences updated successfully'
                })
                
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Invalid endpoint'
                }, status=400)
                
        except Exception as e:
            logger.error(f"Error in OptimizedAPIView POST: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Internal server error'
            }, status=500)


def get_optimized_question_list(exam_id):
    """
    Optimized function to get question list for an exam
    """
    try:
        # Get questions with optimized queries
        questions = Question_DB.objects.filter(
            questionpaper__id=exam_id,
            is_active=True
        ).select_related('professor').order_by('qno')
        
        return questions
    except Exception as e:
        logger.error(f"Error in get_optimized_question_list: {e}")
        return Question_DB.objects.none()


def get_student_performance_stats(student_id):
    """
    Get comprehensive performance statistics for a student
    """
    try:
        # Get all student exams with optimized queries
        student_exams = StuExam_DB.objects.filter(
            student_id=student_id
        ).select_related('qpaper').prefetch_related('questions')
        
        # Calculate statistics
        total_exams = student_exams.count()
        completed_exams = student_exams.filter(completed=1).count()
        avg_score = student_exams.aggregate(avg_score=Avg('score'))['avg_score'] or 0
        
        # Get performance by subject (if you have subject categorization)
        subject_performance = {}
        for exam in student_exams:
            if exam.qpaper:
                subject = exam.qpaper.qPaperTitle.split()[0]  # Simple subject extraction
                if subject not in subject_performance:
                    subject_performance[subject] = {'total': 0, 'scores': []}
                subject_performance[subject]['total'] += 1
                subject_performance[subject]['scores'].append(exam.score)
        
        # Calculate averages for each subject
        for subject in subject_performance:
            scores = subject_performance[subject]['scores']
            subject_performance[subject]['avg_score'] = sum(scores) / len(scores) if scores else 0
        
        return {
            'total_exams': total_exams,
            'completed_exams': completed_exams,
            'completion_rate': (completed_exams / total_exams * 100) if total_exams > 0 else 0,
            'avg_score': round(avg_score, 2),
            'subject_performance': subject_performance
        }
        
    except Exception as e:
        logger.error(f"Error in get_student_performance_stats: {e}")
        return {
            'total_exams': 0,
            'completed_exams': 0,
            'completion_rate': 0,
            'avg_score': 0,
            'subject_performance': {}
        }
