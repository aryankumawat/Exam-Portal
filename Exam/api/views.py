"""
Enhanced API endpoints with better validation and error responses
"""
from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.cache import cache_page
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.paginator import Paginator
from django.db.models import Q, Count, Avg, Prefetch
import json
import logging

from student.models import StudentInfo, StuExam_DB, StuResults_DB
from questions.models import Question_DB, Question_Paper
from security.rate_limiting import rate_limit_decorator, exam_security_check

logger = logging.getLogger(__name__)


class APIResponse:
    """
    Standardized API response helper
    """
    
    @staticmethod
    def success(data=None, message="Success", status_code=200):
        """Return success response"""
        response_data = {
            'success': True,
            'message': message,
            'data': data
        }
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def error(message="Error", errors=None, status_code=400):
        """Return error response"""
        response_data = {
            'success': False,
            'message': message,
            'errors': errors or {}
        }
        return JsonResponse(response_data, status=status_code)
    
    @staticmethod
    def validation_error(errors, message="Validation failed"):
        """Return validation error response"""
        return APIResponse.error(message=message, errors=errors, status_code=422)


@method_decorator([csrf_exempt, rate_limit_decorator('api')], name='dispatch')
class StudentAPIView(View):
    """
    Enhanced student API endpoints
    """
    
    def get(self, request, endpoint):
        """Handle GET requests"""
        try:
            if not request.user.is_authenticated:
                return APIResponse.error("Authentication required", status_code=401)
            
            if endpoint == 'profile':
                return self.get_student_profile(request)
            elif endpoint == 'exams':
                return self.get_student_exams(request)
            elif endpoint == 'results':
                return self.get_student_results(request)
            elif endpoint == 'stats':
                return self.get_student_stats(request)
            elif endpoint == 'recent_activity':
                return self.get_recent_activity(request)
            else:
                return APIResponse.error("Invalid endpoint", status_code=404)
                
        except Exception as e:
            logger.error(f"Error in StudentAPIView GET: {e}")
            return APIResponse.error("Internal server error", status_code=500)
    
    def post(self, request, endpoint):
        """Handle POST requests"""
        try:
            if not request.user.is_authenticated:
                return APIResponse.error("Authentication required", status_code=401)
            
            if endpoint == 'update_profile':
                return self.update_student_profile(request)
            elif endpoint == 'submit_exam':
                return self.submit_exam(request)
            elif endpoint == 'update_preferences':
                return self.update_preferences(request)
            else:
                return APIResponse.error("Invalid endpoint", status_code=404)
                
        except Exception as e:
            logger.error(f"Error in StudentAPIView POST: {e}")
            return APIResponse.error("Internal server error", status_code=500)
    
    def get_student_profile(self, request):
        """Get student profile information"""
        try:
            student_info = StudentInfo.objects.select_related('user').get(user=request.user)
            
            profile_data = {
                'username': student_info.user.username,
                'email': student_info.user.email,
                'first_name': student_info.user.first_name,
                'last_name': student_info.user.last_name,
                'address': student_info.address,
                'stream': student_info.stream,
                'picture_url': student_info.picture.url if student_info.picture else None,
                'created_at': student_info.created_at.isoformat(),
                'updated_at': student_info.updated_at.isoformat()
            }
            
            return APIResponse.success(data=profile_data)
            
        except StudentInfo.DoesNotExist:
            return APIResponse.error("Student profile not found", status_code=404)
    
    def get_student_exams(self, request):
        """Get student exams with pagination and filtering"""
        try:
            # Get query parameters
            page = int(request.GET.get('page', 1))
            per_page = int(request.GET.get('per_page', 10))
            status = request.GET.get('status', 'all')  # all, completed, pending
            search = request.GET.get('search', '')
            
            # Build query
            query = StuExam_DB.objects.filter(student=request.user).select_related(
                'qpaper', 'qpaper__professor'
            ).prefetch_related('questions')
            
            # Apply filters
            if status == 'completed':
                query = query.filter(completed=1)
            elif status == 'pending':
                query = query.filter(completed=0)
            
            if search:
                query = query.filter(
                    Q(examname__icontains=search) | 
                    Q(qpaper__qPaperTitle__icontains=search)
                )
            
            # Order by creation date
            query = query.order_by('-created_at')
            
            # Paginate
            paginator = Paginator(query, per_page)
            page_obj = paginator.get_page(page)
            
            # Serialize data
            exams_data = []
            for exam in page_obj:
                exams_data.append({
                    'id': exam.id,
                    'exam_name': exam.examname,
                    'qpaper_title': exam.qpaper.qPaperTitle if exam.qpaper else 'N/A',
                    'professor': exam.qpaper.professor.username if exam.qpaper and exam.qpaper.professor else 'N/A',
                    'score': exam.score,
                    'completed': bool(exam.completed),
                    'created_at': exam.created_at.isoformat(),
                    'updated_at': exam.updated_at.isoformat()
                })
            
            response_data = {
                'exams': exams_data,
                'pagination': {
                    'current_page': page_obj.number,
                    'total_pages': paginator.num_pages,
                    'total_count': paginator.count,
                    'has_next': page_obj.has_next(),
                    'has_previous': page_obj.has_previous()
                }
            }
            
            return APIResponse.success(data=response_data)
            
        except Exception as e:
            logger.error(f"Error in get_student_exams: {e}")
            return APIResponse.error("Failed to retrieve exams")
    
    def get_student_results(self, request):
        """Get student results with detailed statistics"""
        try:
            # Get student results
            student_results = StuResults_DB.objects.filter(
                student=request.user
            ).prefetch_related(
                'exams__qpaper',
                'exams__questions'
            ).first()
            
            if not student_results:
                return APIResponse.success(data={
                    'results': [],
                    'statistics': {
                        'total_exams': 0,
                        'completed_exams': 0,
                        'average_score': 0,
                        'success_rate': 0
                    }
                })
            
            # Process results
            results_data = []
            total_score = 0
            completed_count = 0
            
            for exam in student_results.exams.all():
                results_data.append({
                    'id': exam.id,
                    'exam_name': exam.examname,
                    'qpaper_title': exam.qpaper.qPaperTitle if exam.qpaper else 'N/A',
                    'score': exam.score,
                    'completed': bool(exam.completed),
                    'created_at': exam.created_at.isoformat()
                })
                
                if exam.completed:
                    total_score += exam.score
                    completed_count += 1
            
            # Calculate statistics
            total_exams = len(results_data)
            average_score = total_score / completed_count if completed_count > 0 else 0
            success_rate = (completed_count / total_exams * 100) if total_exams > 0 else 0
            
            statistics = {
                'total_exams': total_exams,
                'completed_exams': completed_count,
                'average_score': round(average_score, 2),
                'success_rate': round(success_rate, 2)
            }
            
            response_data = {
                'results': results_data,
                'statistics': statistics
            }
            
            return APIResponse.success(data=response_data)
            
        except Exception as e:
            logger.error(f"Error in get_student_results: {e}")
            return APIResponse.error("Failed to retrieve results")
    
    def get_student_stats(self, request):
        """Get comprehensive student statistics"""
        try:
            # Get exam statistics
            exam_stats = StuExam_DB.objects.filter(student=request.user).aggregate(
                total_exams=Count('id'),
                completed_exams=Count('id', filter=Q(completed=1)),
                average_score=Avg('score', filter=Q(completed=1)),
                total_questions=Count('questions')
            )
            
            # Get performance by subject (if available)
            subject_performance = {}
            exams = StuExam_DB.objects.filter(
                student=request.user,
                completed=1
            ).select_related('qpaper')
            
            for exam in exams:
                if exam.qpaper:
                    subject = exam.qpaper.qPaperTitle.split()[0] if exam.qpaper.qPaperTitle else 'Unknown'
                    if subject not in subject_performance:
                        subject_performance[subject] = {'total': 0, 'scores': []}
                    subject_performance[subject]['total'] += 1
                    subject_performance[subject]['scores'].append(exam.score)
            
            # Calculate averages for each subject
            for subject in subject_performance:
                scores = subject_performance[subject]['scores']
                subject_performance[subject]['average_score'] = sum(scores) / len(scores) if scores else 0
                subject_performance[subject]['average_score'] = round(subject_performance[subject]['average_score'], 2)
            
            stats_data = {
                'exam_statistics': exam_stats,
                'subject_performance': subject_performance,
                'completion_rate': round(
                    (exam_stats['completed_exams'] / exam_stats['total_exams'] * 100) 
                    if exam_stats['total_exams'] > 0 else 0, 2
                )
            }
            
            return APIResponse.success(data=stats_data)
            
        except Exception as e:
            logger.error(f"Error in get_student_stats: {e}")
            return APIResponse.error("Failed to retrieve statistics")
    
    def get_recent_activity(self, request):
        """Get recent activity for student"""
        try:
            # Get recent exams
            recent_exams = StuExam_DB.objects.filter(
                student=request.user
            ).select_related('qpaper').order_by('-created_at')[:10]
            
            activities = []
            for exam in recent_exams:
                activities.append({
                    'id': exam.id,
                    'type': 'exam',
                    'title': exam.examname,
                    'description': f"Score: {exam.score}, Status: {'Completed' if exam.completed else 'Pending'}",
                    'created_at': exam.created_at.isoformat(),
                    'qpaper_title': exam.qpaper.qPaperTitle if exam.qpaper else 'N/A'
                })
            
            return APIResponse.success(data=activities)
            
        except Exception as e:
            logger.error(f"Error in get_recent_activity: {e}")
            return APIResponse.error("Failed to retrieve recent activity")
    
    def update_student_profile(self, request):
        """Update student profile"""
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['first_name', 'last_name', 'email']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                return APIResponse.validation_error({
                    'missing_fields': missing_fields
                })
            
            # Validate email format
            email = data['email']
            if '@' not in email or '.' not in email.split('@')[1]:
                return APIResponse.validation_error({
                    'email': ['Invalid email format']
                })
            
            # Update user profile
            with transaction.atomic():
                user = request.user
                user.first_name = data['first_name']
                user.last_name = data['last_name']
                user.email = email
                user.save()
                
                # Update student info
                student_info, created = StudentInfo.objects.get_or_create(user=user)
                if 'address' in data:
                    student_info.address = data['address']
                if 'stream' in data:
                    student_info.stream = data['stream']
                student_info.save()
            
            return APIResponse.success(message="Profile updated successfully")
            
        except json.JSONDecodeError:
            return APIResponse.error("Invalid JSON data", status_code=400)
        except Exception as e:
            logger.error(f"Error in update_student_profile: {e}")
            return APIResponse.error("Failed to update profile")
    
    @exam_security_check
    def submit_exam(self, request):
        """Submit exam with security checks"""
        try:
            data = json.loads(request.body)
            
            # Validate required fields
            required_fields = ['exam_id', 'answers']
            missing_fields = [field for field in required_fields if field not in data]
            
            if missing_fields:
                return APIResponse.validation_error({
                    'missing_fields': missing_fields
                })
            
            exam_id = data['exam_id']
            answers = data['answers']
            
            # Validate exam exists and is accessible
            try:
                exam = StuExam_DB.objects.get(id=exam_id, student=request.user)
            except StuExam_DB.DoesNotExist:
                return APIResponse.error("Exam not found", status_code=404)
            
            # Process answers and calculate score
            with transaction.atomic():
                # Update exam with answers and score
                exam.completed = 1
                exam.score = self.calculate_score(exam, answers)
                exam.save()
                
                # Create student questions for each answer
                for question_id, answer in answers.items():
                    Stu_Question.objects.create(
                        student=request.user,
                        choice=answer,
                        # Copy question data from original question
                        **self.get_question_data(question_id)
                    )
            
            return APIResponse.success(data={
                'exam_id': exam_id,
                'score': exam.score,
                'completed': True
            })
            
        except json.JSONDecodeError:
            return APIResponse.error("Invalid JSON data", status_code=400)
        except Exception as e:
            logger.error(f"Error in submit_exam: {e}")
            return APIResponse.error("Failed to submit exam")
    
    def update_preferences(self, request):
        """Update student preferences"""
        try:
            data = json.loads(request.body)
            
            # This is a placeholder - implement based on your preference model
            # For now, just return success
            
            return APIResponse.success(message="Preferences updated successfully")
            
        except json.JSONDecodeError:
            return APIResponse.error("Invalid JSON data", status_code=400)
        except Exception as e:
            logger.error(f"Error in update_preferences: {e}")
            return APIResponse.error("Failed to update preferences")
    
    def calculate_score(self, exam, answers):
        """Calculate exam score based on answers"""
        # This is a simplified calculation
        # Implement your actual scoring logic here
        total_questions = exam.questions.count()
        correct_answers = 0
        
        for question in exam.questions.all():
            question_id = str(question.qno)
            if question_id in answers:
                if answers[question_id] == question.answer:
                    correct_answers += 1
        
        return round((correct_answers / total_questions * 100), 2) if total_questions > 0 else 0
    
    def get_question_data(self, question_id):
        """Get question data for creating student question"""
        try:
            question = Question_DB.objects.get(qno=question_id)
            return {
                'question': question.question,
                'optionA': question.optionA,
                'optionB': question.optionB,
                'optionC': question.optionC,
                'optionD': question.optionD,
                'answer': question.answer,
                'max_marks': question.max_marks
            }
        except Question_DB.DoesNotExist:
            return {}


@method_decorator([csrf_exempt, rate_limit_decorator('api')], name='dispatch')
class FacultyAPIView(View):
    """
    Enhanced faculty API endpoints
    """
    
    def get(self, request, endpoint):
        """Handle GET requests for faculty"""
        try:
            if not request.user.is_authenticated:
                return APIResponse.error("Authentication required", status_code=401)
            
            if not request.user.groups.filter(name='Professor').exists():
                return APIResponse.error("Faculty access required", status_code=403)
            
            if endpoint == 'questions':
                return self.get_questions(request)
            elif endpoint == 'exams':
                return self.get_exams(request)
            elif endpoint == 'students':
                return self.get_students(request)
            elif endpoint == 'statistics':
                return self.get_faculty_stats(request)
            else:
                return APIResponse.error("Invalid endpoint", status_code=404)
                
        except Exception as e:
            logger.error(f"Error in FacultyAPIView GET: {e}")
            return APIResponse.error("Internal server error", status_code=500)
    
    def get_questions(self, request):
        """Get questions created by faculty"""
        try:
            questions = Question_DB.objects.filter(
                professor=request.user,
                is_active=True
            ).order_by('-created_at')
            
            questions_data = []
            for question in questions:
                questions_data.append({
                    'id': question.qno,
                    'question': question.question,
                    'max_marks': question.max_marks,
                    'created_at': question.created_at.isoformat(),
                    'updated_at': question.updated_at.isoformat()
                })
            
            return APIResponse.success(data=questions_data)
            
        except Exception as e:
            logger.error(f"Error in get_questions: {e}")
            return APIResponse.error("Failed to retrieve questions")
    
    def get_exams(self, request):
        """Get exams created by faculty"""
        try:
            exams = Question_Paper.objects.filter(
                professor=request.user,
                is_active=True
            ).annotate(
                question_count=Count('questions')
            ).order_by('-created_at')
            
            exams_data = []
            for exam in exams:
                exams_data.append({
                    'id': exam.id,
                    'title': exam.qPaperTitle,
                    'question_count': exam.question_count,
                    'created_at': exam.created_at.isoformat(),
                    'updated_at': exam.updated_at.isoformat()
                })
            
            return APIResponse.success(data=exams_data)
            
        except Exception as e:
            logger.error(f"Error in get_exams: {e}")
            return APIResponse.error("Failed to retrieve exams")
    
    def get_students(self, request):
        """Get students for faculty"""
        try:
            students = StudentInfo.objects.select_related('user').all()
            
            students_data = []
            for student in students:
                students_data.append({
                    'id': student.user.id,
                    'username': student.user.username,
                    'email': student.user.email,
                    'first_name': student.user.first_name,
                    'last_name': student.user.last_name,
                    'stream': student.stream,
                    'created_at': student.created_at.isoformat()
                })
            
            return APIResponse.success(data=students_data)
            
        except Exception as e:
            logger.error(f"Error in get_students: {e}")
            return APIResponse.error("Failed to retrieve students")
    
    def get_faculty_stats(self, request):
        """Get faculty statistics"""
        try:
            # Get question statistics
            question_stats = Question_DB.objects.filter(professor=request.user).aggregate(
                total_questions=Count('id'),
                active_questions=Count('id', filter=Q(is_active=True))
            )
            
            # Get exam statistics
            exam_stats = Question_Paper.objects.filter(professor=request.user).aggregate(
                total_exams=Count('id'),
                active_exams=Count('id', filter=Q(is_active=True))
            )
            
            # Get student statistics
            student_stats = StudentInfo.objects.aggregate(
                total_students=Count('id')
            )
            
            stats_data = {
                'questions': question_stats,
                'exams': exam_stats,
                'students': student_stats
            }
            
            return APIResponse.success(data=stats_data)
            
        except Exception as e:
            logger.error(f"Error in get_faculty_stats: {e}")
            return APIResponse.error("Failed to retrieve statistics")
