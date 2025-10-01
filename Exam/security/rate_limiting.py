"""
Rate limiting and security enhancements for the exam portal
"""
from django.core.cache import cache
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from django.conf import settings
import time
import hashlib
import logging

logger = logging.getLogger(__name__)

class RateLimitMiddleware(MiddlewareMixin):
    """
    Rate limiting middleware to prevent abuse
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Rate limits (requests per minute)
        self.rate_limits = {
            'login': 5,  # 5 login attempts per minute
            'register': 3,  # 3 registration attempts per minute
            'exam_submit': 10,  # 10 exam submissions per minute
            'api': 60,  # 60 API calls per minute
            'default': 100,  # 100 requests per minute for other endpoints
        }
        super().__init__(get_response)
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def get_rate_limit_key(self, request, endpoint_type='default'):
        """Generate rate limit key for caching"""
        ip = self.get_client_ip(request)
        user_id = getattr(request.user, 'id', 'anonymous')
        return f"rate_limit:{endpoint_type}:{ip}:{user_id}"
    
    def is_rate_limited(self, request, endpoint_type='default'):
        """Check if request is rate limited"""
        key = self.get_rate_limit_key(request, endpoint_type)
        current_time = int(time.time())
        minute = current_time // 60
        
        # Get current count for this minute
        cache_key = f"{key}:{minute}"
        current_count = cache.get(cache_key, 0)
        
        # Get rate limit for this endpoint type
        rate_limit = self.rate_limits.get(endpoint_type, self.rate_limits['default'])
        
        if current_count >= rate_limit:
            return True
        
        # Increment counter
        cache.set(cache_key, current_count + 1, 60)  # Expire after 1 minute
        return False
    
    def get_endpoint_type(self, request):
        """Determine endpoint type for rate limiting"""
        path = request.path
        
        if 'login' in path:
            return 'login'
        elif 'register' in path:
            return 'register'
        elif 'submit' in path or 'exam' in path:
            return 'exam_submit'
        elif 'api' in path:
            return 'api'
        else:
            return 'default'
    
    def process_request(self, request):
        """Process request for rate limiting"""
        if request.method in ['POST', 'PUT', 'DELETE']:
            endpoint_type = self.get_endpoint_type(request)
            
            if self.is_rate_limited(request, endpoint_type):
                logger.warning(f"Rate limit exceeded for {self.get_client_ip(request)} on {request.path}")
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': 60
                }, status=429)
        
        return None


class SecurityHeadersMiddleware(MiddlewareMixin):
    """
    Add security headers to responses
    """
    
    def process_response(self, request, response):
        """Add security headers"""
        # Content Security Policy
        response['Content-Security-Policy'] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com https://cdnjs.cloudflare.com; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            "frame-ancestors 'none';"
        )
        
        # X-Frame-Options
        response['X-Frame-Options'] = 'DENY'
        
        # X-Content-Type-Options
        response['X-Content-Type-Options'] = 'nosniff'
        
        # X-XSS-Protection
        response['X-XSS-Protection'] = '1; mode=block'
        
        # Referrer Policy
        response['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        
        # Permissions Policy
        response['Permissions-Policy'] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "speaker=()"
        )
        
        return response


class ExamSecurityMiddleware(MiddlewareMixin):
    """
    Security middleware specific to exam functionality
    """
    
    def process_request(self, request):
        """Check for exam security violations"""
        if 'exam' in request.path and request.method == 'POST':
            # Check for suspicious activity
            if self.detect_suspicious_activity(request):
                logger.warning(f"Suspicious activity detected from {self.get_client_ip(request)}")
                return JsonResponse({
                    'error': 'Suspicious activity detected. Exam submission blocked.',
                    'code': 'SECURITY_VIOLATION'
                }, status=403)
        
        return None
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def detect_suspicious_activity(self, request):
        """Detect suspicious activity during exams"""
        # Check for rapid submissions (less than 1 second between requests)
        ip = self.get_client_ip(request)
        cache_key = f"exam_submission:{ip}"
        last_submission = cache.get(cache_key)
        
        if last_submission:
            time_diff = time.time() - last_submission
            if time_diff < 1:  # Less than 1 second
                return True
        
        # Store current submission time
        cache.set(cache_key, time.time(), 300)  # 5 minutes
        
        # Check for multiple tabs/windows (basic detection)
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        if 'headless' in user_agent.lower() or 'bot' in user_agent.lower():
            return True
        
        return False


def rate_limit_decorator(endpoint_type='default', rate_limit=None):
    """
    Decorator for rate limiting specific views
    """
    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            # Get rate limit for this endpoint
            limit = rate_limit or RateLimitMiddleware.rate_limits.get(endpoint_type, 100)
            
            # Check rate limit
            middleware = RateLimitMiddleware(None)
            if middleware.is_rate_limited(request, endpoint_type):
                return JsonResponse({
                    'error': 'Rate limit exceeded. Please try again later.',
                    'retry_after': 60
                }, status=429)
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def exam_security_check(view_func):
    """
    Decorator for exam security checks
    """
    def wrapper(request, *args, **kwargs):
        if request.method == 'POST' and 'exam' in request.path:
            # Check for suspicious activity
            middleware = ExamSecurityMiddleware(None)
            if middleware.detect_suspicious_activity(request):
                logger.warning(f"Exam security violation from {middleware.get_client_ip(request)}")
                return JsonResponse({
                    'error': 'Security violation detected. Action blocked.',
                    'code': 'SECURITY_VIOLATION'
                }, status=403)
        
        return view_func(request, *args, **kwargs)
    return wrapper


class IPWhitelistMiddleware(MiddlewareMixin):
    """
    IP whitelist middleware for admin access
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Add trusted IPs here
        self.whitelisted_ips = getattr(settings, 'TRUSTED_IPS', [
            '127.0.0.1',
            '::1',
            'localhost'
        ])
        super().__init__(get_response)
    
    def get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def process_request(self, request):
        """Check IP whitelist for admin access"""
        if request.path.startswith('/admin/'):
            ip = self.get_client_ip(request)
            if ip not in self.whitelisted_ips:
                logger.warning(f"Unauthorized admin access attempt from {ip}")
                return JsonResponse({
                    'error': 'Access denied. IP not whitelisted.',
                    'code': 'IP_NOT_WHITELISTED'
                }, status=403)
        
        return None
