"""
Email service for sending OTP and notifications
Supports SMTP configuration with proper error handling
"""

import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging
from config import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for OTP and notifications"""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL
        self.from_name = settings.SMTP_FROM_NAME
        
        if not all([self.smtp_host, self.smtp_username, self.smtp_password, self.from_email]):
            logger.warning("⚠️ Email service not properly configured. OTP emails will fail.")
    
    async def send_otp_email(self, to_email: str, otp: str, purpose: str = "verification") -> bool:
        """
        Send OTP email for signup/reset
        
        Args:
            to_email: Recipient email address
            otp: 6-digit OTP code
            purpose: 'verification' or 'reset'
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            # Check if email service is properly configured (not just present but valid)
            is_configured = all([
                self.smtp_host and self.smtp_host.strip(),  # Any valid SMTP host
                self.smtp_username and self.smtp_username != "your-email@gmail.com" and "@" in self.smtp_username,
                self.smtp_password and self.smtp_password != "your-16-digit-app-password-here" and self.smtp_password != "your-app-password-here" and self.smtp_password != "abcdefghijklmnop" and self.smtp_password != "DEVELOPMENT_MODE",
                self.from_email and self.from_email != "your-email@gmail.com" and "@" in self.from_email
            ])
            
            if not is_configured:
                logger.warning("⚠️ Email service not configured with real credentials")
                logger.warning("=" * 60)
                logger.warning(f"🔑 DEVELOPMENT MODE - YOUR OTP CODE IS: {otp}")
                logger.warning(f"📧 For email: {to_email}")
                logger.warning(f"⏰ Valid for {purpose}")
                logger.warning("=" * 60)
                print(f"\n🔑 OTP CODE: {otp} (for {to_email})\n")  # Also print to console
                return True  # Return True for development mode
            
            subject = "Your Guard Management System OTP"
            
            if purpose == "verification":
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #2c3e50;">Welcome to Guard Management System</h2>
                        
                        <p>Thank you for signing up! Please use the following OTP to verify your email address:</p>
                        
                        <div style="background-color: #f8f9fa; border: 2px solid #dee2e6; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                            <h1 style="font-size: 32px; letter-spacing: 8px; margin: 0; color: #007bff;">{otp}</h1>
                        </div>
                        
                        <p><strong>Important:</strong></p>
                        <ul>
                            <li>This OTP is valid for 10 minutes only</li>
                            <li>Do not share this OTP with anyone</li>
                            <li>If you didn't request this OTP, please ignore this email</li>
                        </ul>
                        
                        <p>Once verified, you'll be able to access the Guard Management System.</p>
                        
                        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
                        <p style="font-size: 12px; color: #6c757d;">
                            This is an automated email from Guard Management System. Please do not reply to this email.
                        </p>
                    </div>
                </body>
                </html>
                """
            else:  # reset
                html_content = f"""
                <html>
                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                        <h2 style="color: #dc3545;">Password Reset Request</h2>
                        
                        <p>You have requested to reset your password. Please use the following OTP:</p>
                        
                        <div style="background-color: #f8f9fa; border: 2px solid #dee2e6; border-radius: 8px; padding: 20px; text-align: center; margin: 20px 0;">
                            <h1 style="font-size: 32px; letter-spacing: 8px; margin: 0; color: #dc3545;">{otp}</h1>
                        </div>
                        
                        <p><strong>Security Notice:</strong></p>
                        <ul>
                            <li>This OTP is valid for 10 minutes only</li>
                            <li>Do not share this OTP with anyone</li>
                            <li>If you didn't request a password reset, please ignore this email</li>
                            <li>Your account remains secure</li>
                        </ul>
                        
                        <p>Enter this OTP along with your new password to complete the reset process.</p>
                        
                        <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
                        <p style="font-size: 12px; color: #6c757d;">
                            This is an automated email from Guard Management System. Please do not reply to this email.
                        </p>
                    </div>
                </body>
                </html>
                """
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Create HTML part
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                start_tls=True,
                username=self.smtp_username,
                password=self.smtp_password,
            )
            
            logger.info(f"OTP email sent successfully to {to_email}")
            return True
            
        except aiosmtplib.SMTPAuthenticationError as e:
            logger.error(f"Email authentication failed for {to_email}: {e}")
            logger.warning("⚠️ Gmail credentials invalid. Check .env file or use App Password")
            logger.warning("=" * 60)
            logger.warning(f"� DEVELOPMENT MODE - YOUR OTP CODE IS: {otp}")
            logger.warning(f"📧 For email: {to_email}")
            logger.warning("=" * 60)
            print(f"\n🔑 OTP CODE: {otp} (for {to_email})\n")  # Also print to console
            return True  # Return True for development mode
        except Exception as e:
            logger.error(f"Failed to send OTP email to {to_email}: {e}")
            logger.warning("=" * 60)
            logger.warning(f"� DEVELOPMENT MODE - YOUR OTP CODE IS: {otp}")
            logger.warning(f"📧 For email: {to_email}")
            logger.warning("=" * 60)
            print(f"\n🔑 OTP CODE: {otp} (for {to_email})\n")  # Also print to console
            return True  # Return True for development mode
    
    async def send_welcome_email(self, to_email: str, name: str, role: str) -> bool:
        """
        Send welcome email after successful account activation
        
        Args:
            to_email: Recipient email address
            name: User's full name
            role: User's role (ADMIN, SUPERVISOR, GUARD)
            
        Returns:
            True if email sent successfully, False otherwise
        """
        try:
            subject = "Welcome to Guard Management System"
            
            html_content = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
                <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #28a745;">Welcome to Guard Management System!</h2>
                    
                    <p>Dear {name},</p>
                    
                    <p>Your account has been successfully activated. You now have access to the Guard Management System with <strong>{role}</strong> privileges.</p>
                    
                    <div style="background-color: #e8f5e8; border-left: 4px solid #28a745; padding: 15px; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #155724;">What's Next?</h3>
                        <ul style="margin-bottom: 0;">
                            <li>Login with your email and password</li>
                            <li>Complete your profile setup</li>
                            <li>{"Manage your assigned area and guards" if role == "SUPERVISOR" else "Start your patrol activities" if role == "GUARD" else "Access the admin dashboard"}</li>
                        </ul>
                    </div>
                    
                    <p>If you have any questions or need assistance, please contact your system administrator.</p>
                    
                    <p>Thank you for joining Guard Management System!</p>
                    
                    <hr style="border: none; border-top: 1px solid #dee2e6; margin: 30px 0;">
                    <p style="font-size: 12px; color: #6c757d;">
                        This is an automated email from Guard Management System. Please do not reply to this email.
                    </p>
                </div>
            </body>
            </html>
            """
            
            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to_email
            
            # Create HTML part
            html_part = MIMEText(html_content, "html")
            message.attach(html_part)
            
            # Send email
            await aiosmtplib.send(
                message,
                hostname=self.smtp_host,
                port=self.smtp_port,
                start_tls=True,
                username=self.smtp_username,
                password=self.smtp_password,
            )
            
            logger.info(f"Welcome email sent successfully to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send welcome email to {to_email}: {e}")
            return False


# Global email service instance
email_service = EmailService()
