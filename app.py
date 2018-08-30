from flask import Flask, session, url_for, render_template, request, redirect
import shelve
import time
app = Flask("VoteApp")
DB = shelve.open("db", writeback=True)
class BadRequest:
  def __new__(self, message="Bad Request", code=400):
    return ('<pre style="color: red">Error: %s' % message), code

def clean():
  """Cleans the database
  """

  print(list(DB.items()))
  DB.clear()
  DB.sync()
# clean()

@app.route("/", methods=["GET"])
def index():
  """Index page controls login signup and messages via GET request
  """
  if request.method == "GET":
    # If it has message, ONLY in case of logged out!
    if request.args.get("error") or request.args.get("msg"):
      return render_template("index.html", error=request.args.get("error"), msg=request.args.get("msg"))
    
    # if logged in, check the type of user and present the view accordingly
    type_ = session.get("type", None)
    if type_:
      if type_ == "admin":
        return redirect(url_for("admin_dash"))
      elif type_ == "user":
        return redirect(url_for("user_dash"))

      return BadRequest("Who are you?", 400)
    # if Don't have any message, and don't have any logins, present simple index page
    else:
      return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
  """The Login/register endpoint
  Behaves according to the button pressed.
  """
  # All fields must be entered
  if all(request.form.values()):
    if request.form["action"] == "LogOut":  
      session.clear()
      return redirect(url_for("index", msg="Successfully LoggedOut!"),code=303)

    uid, passwd = request.form["uid"], request.form["password"]
    if not(uid and passwd):
      return "Enter User ID and Password <a href='%s'>Back</a>" % url_for("index"), 400

    if request.form['action'] == "Login":
      if uid in DB.get("users", []):
        # Password authentication
        if passwd == DB["users"][uid]["password"]:
          session["uid"] = uid
          session["type"] = DB["users"][uid]["type"]
          return redirect(url_for("admin_dash"))
        else:
          return BadRequest("Incorrect login password! <a href='%s'>Back</a>" % url_for("index"), 401)
      else:
        return BadRequest("User not found! <a href='%s'>Back</a>" % url_for("index"), 401)
    
    elif request.form["action"] == "Register":
      if uid in DB.get("users", []):
        error = "Sorry, User already exist with the ID. Please try different one!"
        return redirect(url_for(".index", error=error), code=303)
      else:
        type_ = None
        if not DB.get("users"):
          # first run
          DB["users"] = {}
          DB.sync()
          type_ = "admin"  # first user is admin
        if not type_:
          type_ = "user"
        DB["users"][uid]={"password": passwd, "type":type_, "voted":None}  # default to normal user
        DB.sync()
        return redirect(url_for("index", msg="Successfully Registered. Please login!"), code=303)
  else:
    return BadRequest("Enter username and password", 400)
    

@app.route("/user/dashboard/", methods=["GET", "POST"])
def user_dash():
  """User Dashboard view
  """
  uid = session.get("uid", None)
  # if user id is not present in session and/or database(ie. user has been deleted)
  if not uid or uid not in DB.get("users", []):
    # Kick 'em out
    session.clear()
    return redirect(url_for(".index", error="You need to login first."), code=303)
  
  # Both admin and user can access the user view
  if not (session["type"] == "admin" or session["type"] == "user"):
    session.clear()
    return "<script>function Redirect() {  \
        window.location=\"%s\"; \
    } \
    document.write('You are not authorized to view this page. Please <a href=\'%s\'>login</a>.'); \
    setTimeout('Redirect()', 3000); </script>"% tuple(url_for("login"))*2, 401
  
  # Check whom did the user vote
  user_voted = DB["users"][uid].get("voted", None)

  # if user voted for somebody not in nominee list, discard the vote
  if user_voted not in DB.get("nominees", []):
    DB["users"][uid]["voted"] = None
    user_voted = None
    DB.sync()

  if request.method=="GET":
    return render_template("user_dashboard.html",
                           DB=DB, name=session["uid"],
                           voted=user_voted
                          )
  
  elif request.method=="POST":
    candidate_voted = request.form["action"]
    # Candidate should be in nominee list
    if candidate_voted and candidate_voted in DB['nominees']:
      # If user has already voted, he can't change the vote.
      if user_voted:
        return "<script>alert('You can only vote once and you already have voted for %s'); window.location = window.location.href;</script>" % user_voted
      else:
        DB["users"][uid]["voted"] = candidate_voted
        DB["nominees"][candidate_voted] += 1
      DB.sync()
      return redirect(url_for("user_dash"))
    else:
      return BadRequest("Candidate does not exist!", 400)


@app.route("/admin/dashboard/", methods=["GET", "POST"])
def admin_dash():
  uid = session.get("uid", None)
  # Admin should be there in the users list
  if not uid or uid not in DB.get("users", []):
    session.clear()
    return redirect(url_for(".index", error="You need to login first."),code=303)
  
  # only admin can access the admin view
  if session["type"] != "admin":
    red_url = '"'+url_for("user_dash")+'"' if session["type"] == "user" else "window.history.back();"
    return "<script>function Redirect() {  \
        window.location=%s \
    } \
    document.write('You are not authorized to view this page. You will be redirected now.'); \
    setTimeout('Redirect()', 3000); </script>" % red_url, 403
  
  if request.method=="GET":
    return render_template("admin_dashboard.html", DB=DB, name=session["uid"])
  
  elif request.method=="POST":
    # Add a nominee in election
    if request.form["action"] == "add":
      nominee_name = request.form["nid"]
      if nominee_name.strip():
        if DB.get("nominees"):
          if nominee_name in DB.get("nominees", []):
            return "<script> alert('Nominee %s already Exist!'); window.location = window.location.href;</script>" % nominee_name
          DB["nominees"][nominee_name] = 0
        else:
          # first nominee
          DB["nominees"] = {nominee_name: 0}
        DB.sync()
        return redirect(url_for("admin_dash"))
      else:
        return BadRequest("Enter Nominee Name!", 400)
    
    # Delete candidate
    elif request.form["action"].startswith("d_"):
      nominee_name = "_".join(request.form["action"].split("_")[1:])
      # Delete from the list
      del DB["nominees"][nominee_name]
      # Void the vote if any user voted for that candidate and allow user
      # to cast the vote again
      for user in DB.get("users", []):
        voted = DB["users"][user].get("voted")
        if voted and voted == nominee_name:
          DB["users"][user]["voted"] = None
      DB.sync()
      return redirect(url_for("admin_dash"))
    else:
      return BadRequest("Bad Request!", 400)
      

  
if __name__ == "__main__":
  app.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
  app.run()