from django.urls import path
from . import views
from django.conf.urls.static import static
from django.conf import settings
from django.contrib.auth import views as auth_views
from .views import GPasswordChangeView
urlpatterns = [
    path('', views.signin, name='landingpage'),
    path('signup', views.signup, name="signup"),
    path('signin', views.signin, name="signin"),
    path('signout', views.signout, name='signout'),
    path('landingpage', views.landingpage, name='landingpage'),
    path('electionlist', views.electionlist, name="electionlist"),
    path('electiondetail/<int:election_id>', views.electiondetail, name="electiondetail"),
    path('votecandidate', views.votecandidate, name='votecandidate'),
    path("results/<int:election_id>/", views.results_page, name="results"),
    path("results", views.results_index, name="results"),
    path("results/<int:election_id>/json/", views.results_json, name="results_json"),
        path("changepassword", auth_views.PasswordChangeView.as_view(
        template_name="changepassword.html",
        success_url="password/done/"
    ), name="passwordchange"),

    path("password/done/", auth_views.PasswordChangeDoneView.as_view(
        template_name="changepassworddone.html"
    ), name="passwordchangedone"),
    path("password/", GPasswordChangeView.as_view(), name="passwordchange"),


] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
