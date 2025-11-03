import streamlit as st
import hashlib
import os

class AuthManager:
    def __init__(self):
        # Anchor password file to project folder to avoid per-CWD duplicates
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.password_file = os.path.join(base_dir, "data", "password.txt")
        self._initialize_password()
    
    def _initialize_password(self):
        """Initialize password file with default password if not exists."""
        data_dir = os.path.dirname(self.password_file)
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        
        if not os.path.exists(self.password_file):
            default_password = "admin123"
            hashed = self._hash_password(default_password)
            with open(self.password_file, 'w') as f:
                f.write(hashed)
    
    def _hash_password(self, password):
        """Hash password using SHA256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def verify_password(self, password):
        """Verify if password matches stored hash."""
        try:
            with open(self.password_file, 'r') as f:
                stored_hash = f.read().strip()
            
            input_hash = self._hash_password(password)
            return input_hash == stored_hash
        except Exception as e:
            st.error(f"Error verifying password: {str(e)}")
            return False
    
    def change_password(self, old_password, new_password):
        """Change password if old password is correct."""
        if self.verify_password(old_password):
            try:
                new_hash = self._hash_password(new_password)
                with open(self.password_file, 'w') as f:
                    f.write(new_hash)
                return True
            except Exception as e:
                st.error(f"Error changing password: {str(e)}")
                return False
        return False
    
    def show_login_page(self):
        """Display login page."""
        st.title("🔒 JENENDRA PRESS INVENTORY")
        st.markdown("### Please login to continue")
        
        st.info("Default password: **admin123**")
        
        with st.form("login_form"):
            password = st.text_input("Password", type="password", placeholder="Enter your password")
            submit = st.form_submit_button("Login", type="primary")
            
            if submit:
                if password:
                    if self.verify_password(password):
                        st.session_state.authenticated = True
                        st.success("Login successful!")
                        st.rerun()
                    else:
                        st.error("Incorrect password. Please try again.")
                else:
                    st.error("Please enter a password.")
        
        st.markdown("---")
        st.markdown("*Please change the default password after first login from Settings.*")
    
    def show_change_password_page(self):
        """Display change password page."""
        st.subheader("Change Password")
        
        with st.form("change_password_form"):
            old_password = st.text_input("Current Password", type="password")
            new_password = st.text_input("New Password", type="password")
            confirm_password = st.text_input("Confirm New Password", type="password")
            
            submit = st.form_submit_button("Change Password", type="primary")
            
            if submit:
                if not old_password or not new_password or not confirm_password:
                    st.error("Please fill in all fields.")
                elif new_password != confirm_password:
                    st.error("New passwords do not match.")
                elif len(new_password) < 6:
                    st.error("New password must be at least 6 characters long.")
                else:
                    if self.change_password(old_password, new_password):
                        st.success("Password changed successfully!")
                    else:
                        st.error("Current password is incorrect.")
    
    def logout(self):
        """Logout user."""
        st.session_state.authenticated = False
        st.rerun()
