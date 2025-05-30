from shiny import ui, reactive, render, Session, Inputs, Outputs
import sqlite3
from typing import Optional
from auth.auth_db import create_user, verify_user, create_session, validate_session, DB_PATH

class AuthManager:
    def __init__(self):
        self.current_user = reactive.Value(None)
        self.modal_state = reactive.Value("hidden")

    def server(self, input: Inputs, output: Outputs, session: Session):
        # Handle session initialization from cookies
        @reactive.Effect
        def _init_session():
            cookie = input.cookie_session()  # Get from hidden input
            if cookie:
                user_id = validate_session(cookie)
                if user_id:
                    self.current_user.set({
                        "id": user_id,
                        "session_id": cookie
                    })

        # Login handler
        @reactive.Effect
        @reactive.event(input.auth_login)
        def _handle_login():
            username = input.auth_username()
            password = input.auth_password()
            
            user_id = verify_user(username, password)
            if user_id:
                session_id = create_session(user_id)
                self.current_user.set({
                    "id": user_id,
                    "username": username,
                    "session_id": session_id
                })
                ui.modal_remove()
                ui.notification_show("Login successful!", type="message")
                # Set cookie via JavaScript
                session.send_custom_message("set-cookie", {
                    "name": "session_id",
                    "value": session_id,
                    "days": 1
                })
                ui.update_text("auth_username", value="")
                ui.update_text("auth_password", value="")
            else:
                ui.notification_show("Invalid credentials", type="error")

        # Logout handler
        @reactive.Effect
        @reactive.event(input.auth_logout)
        def _handle_logout():
            if self.current_user.get():
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute(
                        "DELETE FROM sessions WHERE session_id = ?",
                        (self.current_user.get()["session_id"],))
                    conn.commit()
                # Clear cookie via JavaScript
                session.send_custom_message("delete-cookie", {
                    "name": "session_id"
                })
                self.current_user.set(None)
                ui.notification_show("Logged out successfully", type="message")

        # Modal visibility control
        @reactive.Effect
        @reactive.event(input.show_auth_modal)
        def _handle_modal():
            action = input.show_auth_modal()
            self.modal_state.set(action if action in ["login", "register"] else "hidden")

        # Modal UI renderer
        @output
        @render.ui
        def auth_modal():
            if self.modal_state.get() == "hidden":
                return None

            # Define custom CSS within the modal content
            modal_style = ui.tags.style("""
                .auth-modal .form-control {
                    border-radius: 0.5rem;
                    border: 1px solid var(--bs-success);
                    padding: 1rem;
                }
                .auth-modal .form-control:focus {
                    border-color: var(--bs-success);
                    box-shadow: 0 0 0 0.25rem rgba(25, 135, 84, 0.25);
                }
                .auth-modal .input-group-text {
                    background-color: var(--bs-success-bg-subtle);
                    border-color: var(--bs-success);
                    border-right: none;
                }
                .auth-modal .nav-link.active {
                    border-color: var(--bs-success) !important;
                    color: var(--bs-success) !important;
                }
            """)

            return ui.modal(
                ui.div(
                    # Include style tag first
                    modal_style,
                    
                    # Tabbed content
                    ui.navset_tab(
                        ui.nav_panel(
                            "Login",
                            ui.div(
                                ui.div(
                                    ui.tags.i(class_="bi bi-person-circle display-4 text-success mb-4"),
                                    class_="text-center"
                                ),
                                ui.div(
                                    ui.div(
                                        ui.span(
                                            ui.tags.i(class_="bi bi-person-fill"),
                                            class_="input-group-text"
                                        ),
                                        ui.input_text("auth_username", "", placeholder="Username"),
                                        class_="input-group mb-3"
                                    ),
                                    ui.div(
                                        ui.span(
                                            ui.tags.i(class_="bi bi-lock-fill"),
                                            class_="input-group-text"
                                        ),
                                        ui.input_password("auth_password", "", placeholder="Password"),
                                        class_="input-group mb-4"
                                    ),
                                    ui.input_action_button(
                                        "auth_login", 
                                        ui.TagList(
                                            ui.tags.i(class_="bi bi-box-arrow-in-right me-2"),
                                            "Sign In"
                                        ),
                                        class_="btn-success w-100"
                                    ),
                                )
                            )
                        ),
                        ui.nav_panel(
                            "Register",
                            ui.div(
                                ui.div(
                                    ui.tags.i(class_="bi bi-person-plus-fill display-4 text-success mb-4"),
                                    class_="text-center"
                                ),
                                ui.div(
                                    ui.div(
                                        ui.span(
                                            ui.tags.i(class_="bi bi-person-fill"),
                                            class_="input-group-text"
                                        ),
                                        ui.input_text("reg_username", "", placeholder="Username"),
                                        class_="input-group mb-3"
                                    ),
                                    ui.div(
                                        ui.span(
                                            ui.tags.i(class_="bi bi-lock-fill"),
                                            class_="input-group-text"
                                        ),
                                        ui.input_password("reg_password", "", placeholder="Password"),
                                        class_="input-group mb-3"
                                    ),
                                    ui.div(
                                        ui.span(
                                            ui.tags.i(class_="bi bi-lock-fill"),
                                            class_="input-group-text"
                                        ),
                                        ui.input_password("reg_confirm", "", placeholder="Confirm Password"),
                                        class_="input-group mb-4"
                                    ),
                                    ui.input_action_button(
                                        "register",
                                        ui.TagList(
                                            ui.tags.i(class_="bi bi-person-add me-2"),
                                            "Create Account"
                                        ),
                                        class_="btn-success w-100"
                                    ),
                                )
                            )
                        ),
                        id="auth_tabs",
                        selected=self.modal_state.get(),
                        header=ui.div(
                            class_="border-bottom border-success mb-4",
                            style="--bs-nav-link-color: var(--bs-success); --bs-nav-tabs-link-active-color: var(--bs-success);"
                        )
                    ),
                    class_="auth-modal"
                ),
                title=None,
                size="m",
                easy_close=True,
                footer=None
            )