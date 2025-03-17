import tkinter as tk
from tkinter import messagebox
import requests
import json
from PIL import Image, ImageTk
import os
class LoginApp:
    def __init__(self, root=None):
        if root is None:
            return
        self.root = root
        self.root.title("Innov8r Login")
        self.root.geometry("600x500")  # Updated screen size
        self.root.configure(bg="#e6f7ff")  # Softer blue background
        
        # Load and add the image at the top
        self.image = Image.open(os.path.join(os.path.dirname(__file__), "res", "innovator.png"))  # Replace with your image path
        self.image = self.image.resize((120, 120), Image.Resampling.LANCZOS)  # Updated for compatibility with new Pillow version
        self.photo = ImageTk.PhotoImage(self.image)
        self.image_label = tk.Label(self.root, image=self.photo, bg="#e6f7ff")
        self.image_label.pack(pady=(20, 10))  # Padding above and below the image

        # Main Frame
        self.main_frame = tk.Frame(self.root, bg="#e6f7ff", padx=40, pady=40)
        self.main_frame.pack(expand=True)

        # Email Label and Entry with horizontal and vertical padding
        self.email_label = tk.Label(self.main_frame, text="Email:", font=("Verdana", 14, "bold"), bg="#e6f7ff", fg="#333", anchor="w", justify="left")
        self.email_label.pack(fill="x", pady=(0, 5))
        self.email_entry = tk.Entry(self.main_frame, font=("Verdana", 12), width=30, highlightbackground="#4CAF50", highlightthickness=2, relief="groove", bd=0)
        self.email_entry.pack(ipadx=10, ipady=5, pady=(0, 15))  # Added ipadx for horizontal padding

        # Password Label and Entry with horizontal and vertical padding
        self.password_label = tk.Label(self.main_frame, text="Password:", font=("Verdana", 14, "bold"), bg="#e6f7ff", fg="#333", anchor="w", justify="left")
        self.password_label.pack(fill="x", pady=(10, 5))
        self.password_entry = tk.Entry(self.main_frame, font=("Verdana", 12), show="*", width=30, highlightbackground="#4CAF50", highlightthickness=2, relief="groove", bd=0)
        self.password_entry.pack(ipadx=10, ipady=5, pady=(0, 20))  # Added ipadx for horizontal padding

        # Login Button
        self.login_button = tk.Button(self.main_frame, 
                                       text="Login", 
                                       font=("Verdana", 12, "bold"), 
                                       bg="#0288d1",  # Stylish blue button
                                       fg="white", 
                                       activebackground="#0277bd", 
                                       activeforeground="white", 
                                       width=20, 
                                       relief="flat")  # Flat style for a modern look
        self.login_button.pack()
        self.login_button.bind("<Button-1>", self.verify_login)
    def clear_placeholder(self, event):
        widget = event.widget
        if widget.get() == "Enter your email" or widget.get() == "Enter your password":
            widget.delete(0, "end")
    def verify_login(self,event):
        email = self.email_entry.get()
        password = self.password_entry.get()
        if(email == "" or password == ""):
            messagebox.showerror("Error", "Please enter email and password.")
            return
        try:
            response = requests.post("https://backend.educobot.com/users/getUser", json={"email": email, "password": password})
            response = response.json()
            print(response)

            if response["userID"]:
                self.save_credentials(response["userID"])
                messagebox.showinfo("Success", "Login successful!", icon='info')
                self.root.destroy()
            elif response["user"]:
                self.save_credentials(response["user"])
                messagebox.showinfo("Success", "Login successful!", icon='info')
                self.root.destroy()
            else:
                messagebox.showerror("Error", "Invalid email or password")
                self.password_entry.delete(0, tk.END)

        except Exception as exception:
            print(exception)
            messagebox.showerror("Error", "Invalid email or password.")
    def save_credentials(self, userId):
        try:
            response = requests.post("https://backend.educobot.com/blockly/get-user-details", json={"userId": userId})
            response = response.json()
            print(response)
            if response["user"]:
                with open("credential.json", "w") as f:
                    json.dump(response, f)

        except Exception as exception:
            print(exception)
            messagebox.showerror("Error", "Invalid email or password.")
    def isLoggedIn(self):
        try:
            with open("credential.json", "r") as f:
                data = json.load(f)
            return True
        except:
            return False

def openLoginScreen(successFunction):
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()
    if(app.isLoggedIn()):
        successFunction()

if __name__ == "__main__":
    root = tk.Tk()
    app = LoginApp(root)
    root.mainloop()
