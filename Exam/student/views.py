from django.shortcuts import render,redirect
from django.views import View
from .forms import StudentForm, StudentInfoForm
from django.contrib.auth.decorators import login_required
from django.contrib import auth
from django.contrib import messages
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode 
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str, DjangoUnicodeDecodeError
from .utils import account_activation_token
from django.core.mail import EmailMessage
import threading
from django.contrib.auth.models import User
from studentPreferences.models import StudentPreferenceModel
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_email
import logging

# Set up logging
logger = logging.getLogger(__name__)

@login_required(login_url='login')
def index(request):
    return render(request,'student/index.html')

@method_decorator([csrf_protect, never_cache], name='dispatch')
class Register(View):
    def get(self, request):
        try:
            student_form = StudentForm()
            student_info_form = StudentInfoForm()
            return render(request, 'student/register.html', {
                'student_form': student_form,
                'student_info_form': student_info_form
            })
        except Exception as e:
            logger.error(f"Error in Register GET: {e}")
            messages.error(request, "An error occurred while loading the registration page. Please try again.")
            return redirect('login')
    
    def post(self, request):
        try:
            # Validate CSRF token
            if not request.POST.get('csrfmiddlewaretoken'):
                messages.error(request, "Invalid request. Please try again.")
                return redirect('register')
            
            # Get form data
            student_form = StudentForm(data=request.POST)
            student_info_form = StudentInfoForm(data=request.POST)
            email = request.POST.get('email', '').strip()
            
            # Additional validation
            if not email:
                messages.error(request, "Email is required.")
                return render(request, 'student/register.html', {
                    'student_form': student_form,
                    'student_info_form': student_info_form
                })
            
            # Validate email format
            try:
                validate_email(email)
            except ValidationError:
                messages.error(request, "Please enter a valid email address.")
                return render(request, 'student/register.html', {
                    'student_form': student_form,
                    'student_info_form': student_info_form
                })
            
            # Check if email already exists
            if User.objects.filter(email=email).exists():
                messages.error(request, "An account with this email already exists.")
                return render(request, 'student/register.html', {
                    'student_form': student_form,
                    'student_info_form': student_info_form
                })
            
            # Validate password strength
            password = request.POST.get('password', '')
            if password:
                try:
                    validate_password(password)
                except ValidationError as e:
                    messages.error(request, f"Password validation failed: {'; '.join(e.messages)}")
                    return render(request, 'student/register.html', {
                        'student_form': student_form,
                        'student_info_form': student_info_form
                    })
            
            if student_form.is_valid() and student_info_form.is_valid():
                with transaction.atomic():
                    # Create user
                    student = student_form.save(commit=False)
                    student.set_password(student.password)
                    student.is_active = True
                    student.save()
                    
                    # Add to Student group
                    try:
                        student_group, created = Group.objects.get_or_create(name='Student')
                        student_group.user_set.add(student)
                    except Exception as e:
                        logger.error(f"Error adding user to Student group: {e}")
                        messages.error(request, "Error creating user account. Please contact support.")
                        return redirect('register')
                    
                    # Create student info
                    student_info = student_info_form.save(commit=False)
                    student_info.user = student
                    if 'picture' in request.FILES:
                        # Validate file size and type
                        picture = request.FILES['picture']
                        if picture.size > 5 * 1024 * 1024:  # 5MB limit
                            messages.error(request, "Profile picture size should be less than 5MB.")
                            return render(request, 'student/register.html', {
                                'student_form': student_form,
                                'student_info_form': student_info_form
                            })
                        student_info.picture = picture
                    student_info.save()
                    
                    # Send activation email
                    try:
                        uidb64 = urlsafe_base64_encode(force_bytes(student.pk))
                        domain = get_current_site(request).domain
                        link = reverse('activate', kwargs={'uidb64': uidb64, 'token': account_activation_token.make_token(student)})
                        activate_url = f'http://{domain}{link}'
                        email_subject = 'Activate your Exam Portal account'
                        email_body = f'''Hi {student.username},

Please use this link to verify your account: {activate_url}

You are receiving this message because you registered on {domain}. If you didn't register, please contact our support team.

Best regards,
Exam Portal Team'''
                        
                        email_message = EmailMessage(
                            email_subject,
                            email_body,
                            'noreply@exam.com',
                            [email],
                        )
                        EmailThread(email_message).start()
                        
                        messages.success(request, "Registered successfully! Please check your email for account activation.")
                        logger.info(f"User {student.username} registered successfully")
                        return redirect('login')
                        
                    except Exception as e:
                        logger.error(f"Error sending activation email: {e}")
                        messages.warning(request, "Account created but activation email could not be sent. Please contact support.")
                        return redirect('login')
            else:
                # Log form errors
                logger.warning(f"Registration form validation failed: {student_form.errors}, {student_info_form.errors}")
                messages.error(request, "Please correct the errors below and try again.")
                return render(request, 'student/register.html', {
                    'student_form': student_form,
                    'student_info_form': student_info_form
                })
                
        except IntegrityError as e:
            logger.error(f"Database integrity error during registration: {e}")
            messages.error(request, "An account with this username or email already exists.")
            return render(request, 'student/register.html', {
                'student_form': student_form,
                'student_info_form': student_info_form
            })
        except Exception as e:
            logger.error(f"Unexpected error during registration: {e}")
            messages.error(request, "An unexpected error occurred. Please try again later.")
            return redirect('register')
    
@method_decorator([csrf_protect, never_cache], name='dispatch')
class LoginView(View):
    def get(self, request):
        try:
            # Check if user is already logged in
            if request.user.is_authenticated:
                return redirect('index')
            return render(request, 'student/login.html')
        except Exception as e:
            logger.error(f"Error in LoginView GET: {e}")
            messages.error(request, "An error occurred while loading the login page. Please try again.")
            return render(request, 'student/login.html')
    
    def post(self, request):
        try:
            # Validate CSRF token
            if not request.POST.get('csrfmiddlewaretoken'):
                messages.error(request, "Invalid request. Please try again.")
                return render(request, 'student/login.html')
            
            username = request.POST.get('username', '').strip()
            password = request.POST.get('password', '')
            
            # Basic validation
            if not username or not password:
                messages.error(request, 'Please fill in all fields.')
                return render(request, 'student/login.html')
            
            # Check for suspicious patterns
            if len(username) > 150 or len(password) > 128:
                messages.error(request, 'Invalid credentials provided.')
                return render(request, 'student/login.html')
            
            # Check if user exists
            try:
                user_exists = User.objects.filter(username=username).exists()
                if user_exists:
                    user_check = User.objects.get(username=username)
                    
                    # Check if user is trying to login as student but is faculty
                    if user_check.is_staff:
                        messages.error(request, "You are trying to login as student, but you have registered as faculty. We are redirecting you to faculty login. If you are having problems logging in, please reset your password or contact admin.")
                        return redirect('faculty-login')
                
                # Authenticate user
                user = auth.authenticate(username=username, password=password)
                
                if user:
                    if user.is_active:
                        # Check if user is in Student group
                        if not user.groups.filter(name='Student').exists():
                            messages.error(request, "Your account is not authorized to access the student portal. Please contact support.")
                            return render(request, 'student/login.html')
                        
                        # Login user
                        auth.login(request, user)
                        
                        # Send login notification email (if enabled)
                        try:
                            student_pref = StudentPreferenceModel.objects.filter(user=request.user).first()
                            send_email = True
                            
                            if student_pref:
                                send_email = student_pref.sendEmailOnLogin
                            
                            if send_email:
                                email_subject = 'You Logged into your Portal account'
                                email_body = f"""Hi {user.username},

You have successfully logged into your Exam Portal account.

If you think someone else logged in, please contact support or reset your password immediately.

You are receiving this message because you have enabled login email notifications in portal settings. If you don't want to receive such emails in the future, please turn off the login email notifications in settings.

Best regards,
Exam Portal Team"""
                                
                                email_message = EmailMessage(
                                    email_subject,
                                    email_body,
                                    'noreply@exam.com',
                                    [user.email],
                                )
                                EmailThread(email_message).start()
                        except Exception as e:
                            logger.warning(f"Error sending login notification email: {e}")
                        
                        messages.success(request, f"Welcome, {user.username}! You are now logged in.")
                        logger.info(f"User {user.username} logged in successfully")
                        
                        # Redirect to next page if specified
                        next_page = request.GET.get('next', 'index')
                        return redirect(next_page)
                    else:
                        messages.error(request, 'Your account is not activated. Please check your email for activation link or contact support.')
                        return render(request, 'student/login.html')
                else:
                    # User doesn't exist or wrong password
                    if user_exists:
                        user_obj = User.objects.get(username=username)
                        if not user_obj.is_active:
                            messages.error(request, 'Account not activated. Please check your email for activation link.')
                        else:
                            messages.error(request, 'Invalid credentials. Please check your username and password.')
                    else:
                        messages.error(request, 'Invalid credentials. Please check your username and password.')
                    
                    return render(request, 'student/login.html')
                    
            except User.DoesNotExist:
                messages.error(request, 'Invalid credentials. Please check your username and password.')
                return render(request, 'student/login.html')
            except Exception as e:
                logger.error(f"Error during authentication: {e}")
                messages.error(request, 'An error occurred during login. Please try again.')
                return render(request, 'student/login.html')
                
        except Exception as e:
            logger.error(f"Unexpected error in LoginView POST: {e}")
            messages.error(request, "An unexpected error occurred. Please try again later.")
            return render(request, 'student/login.html')

@method_decorator([csrf_protect, never_cache], name='dispatch')
class LogoutView(View):
    def post(self, request):
        try:
            if request.user.is_authenticated:
                username = request.user.username
                auth.logout(request)
                messages.success(request, 'You have been successfully logged out.')
                logger.info(f"User {username} logged out successfully")
            else:
                messages.info(request, 'You were not logged in.')
            return redirect('login')
        except Exception as e:
            logger.error(f"Error during logout: {e}")
            messages.error(request, "An error occurred during logout. Please try again.")
            return redirect('login')

class EmailThread(threading.Thread):
	def __init__(self,email):
		self.email = email
		threading.Thread.__init__(self)

	
	def run(self):
		self.email.send(fail_silently = False)

class VerificationView(View):
	def get(self,request,uidb64,token):
		try:
			id = force_str(urlsafe_base64_decode(uidb64))
			user = User.objects.get(pk=id)
			if not account_activation_token.check_token(user,token):
				messages.error(request,"User already Activated. Please Proceed With Login")
				return redirect("login")
			if user.is_active:
				return redirect('login')
			user.is_active = True
			user.save()
			messages.success(request,'Account activated Sucessfully')
			return redirect('login')
		except Exception as e:
			raise e
		return redirect('login')
	
