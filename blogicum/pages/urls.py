from django.urls import path
from django.views.generic import TemplateView


app_name = 'pages'

urlpatterns = [
    path('about/',
         TemplateView.as_view(template_name="pages/about.html"),
         name='about'),
    path('rules/',
         TemplateView.as_view(template_name="pages/rules.html"),
         name='rules')
]

handler404 = 'pages.views.page_not_found'
handler500 = 'pages.views.err_500'
