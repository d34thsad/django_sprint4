from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.core.mail import send_mail
from django.utils.timezone import now
from django.db.models import Count
from django.utils import timezone
from django.views import View
from django.views.generic import (
    ListView,
    DetailView,
    UpdateView,
    CreateView,
    DeleteView,
)

from .models import Post, User, Category, Comment
from .forms import UserForm, PostForm, CommentForm


def post_all_query():
    query_set = (
        Post.objects.select_related(
            "category",
            "location",
            "author",
        )
        .annotate(comment_count=Count("comments"))
        .order_by("-pub_date")
    )
    return query_set


def post_published_query():
    query_set = post_all_query().filter(
        pub_date__lte=timezone.now(),
        is_published=True,
        category__is_published=True,
    )
    return query_set


def get_post_data(post_data):
    post = get_object_or_404(
        Post,
        pk=post_data["pk"],
        pub_date__lte=timezone.now(),
        is_published=True,
        category__is_published=True,
    )
    return post


class CommentMixinView(LoginRequiredMixin, View):
    model = Comment
    template_name = "blog/comment.html"
    pk_url_kwarg = "comment_pk"

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().author != request.user:
            return redirect("blog:post_detail", pk=self.kwargs["pk"])
        get_post_data(self.kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        pk = self.kwargs["pk"]
        return reverse("blog:post_detail", kwargs={"pk": pk})


class MainPostListView(ListView):
    model = Post
    template_name = "blog/index.html"
    queryset = post_published_query()
    paginate_by = 10


class CategoryPostListView(MainPostListView):
    template_name = "blog/category.html"
    category = None

    def get_queryset(self):
        slug = self.kwargs["category_slug"]
        self.category = get_object_or_404(
            Category, slug=slug, is_published=True
        )
        return super().get_queryset().filter(category=self.category)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["category"] = self.category
        return context


class UserPostsListView(MainPostListView):
    template_name = "blog/profile.html"
    author = None

    def get_queryset(self):
        username = self.kwargs["username"]
        self.author = get_object_or_404(User, username=username)
        if self.author == self.request.user:
            return post_all_query().filter(author=self.author)
        return super().get_queryset().filter(author=self.author)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["profile"] = self.author
        return context


class PostDetailView(DetailView):
    model = Post
    template_name = "blog/detail.html"
    post_data = None

    def get_queryset(self):
        self.post_data = get_object_or_404(Post, pk=self.kwargs["pk"])
        if self.post_data.author == self.request.user:
            return post_all_query().filter(pk=self.kwargs["pk"])
        return post_published_query().filter(pk=self.kwargs["pk"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.check_post_data():
            context["flag"] = True
            context["form"] = CommentForm()
        context["comments"] = self.object.comments.all().select_related(
            "author"
        )
        return context

    def check_post_data(self):
        """Вернуть результат проверки поста."""
        return all(
            (
                self.post_data.is_published,
                self.post_data.pub_date <= now(),
                self.post_data.category.is_published,
            )
        )


class UserProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserForm
    template_name = "blog/user.html"

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        username = self.request.user
        return reverse("blog:profile", kwargs={"username": username})


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = "blog/create.html"

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        username = self.request.user
        return reverse("blog:profile", kwargs={"username": username})


class PostUpdateView(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = "blog/create.html"

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().author != request.user:
            return redirect("blog:post_detail", pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_success_url(self):
        pk = self.kwargs["pk"]
        return reverse("blog:post_detail", kwargs={"pk": pk})


class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = Post
    template_name = "blog/create.html"

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().author != request.user:
            return redirect("blog:post_detail", pk=self.kwargs["pk"])
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = PostForm(instance=self.object)
        return context

    def get_success_url(self):
        username = self.request.user
        return reverse_lazy("blog:profile", kwargs={"username": username})


class CommentCreateView(LoginRequiredMixin, CreateView):
    model = Comment
    form_class = CommentForm
    template_name = "blog/comment.html"
    post_data = None

    def dispatch(self, request, *args, **kwargs):
        self.post_data = get_post_data(self.kwargs)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        form.instance.author = self.request.user
        form.instance.post = self.post_data
        if self.post_data.author != self.request.user:
            self.send_author_email()
        return super().form_valid(form)

    def get_success_url(self):
        pk = self.kwargs["pk"]
        return reverse("blog:post_detail", kwargs={"pk": pk})
    
    def send_author_email(self):
        post_url = self.request.build_absolute_uri(self.get_success_url())
        recipient_email = self.post_data.author.email
        subject = "New comment"
        message = (
            f"Пользователь {self.request.user} добавил "
            f"комментарий к посту {self.post_data.title}.\n"
            f"Читать комментарий {post_url}"
        )
        send_mail(
            subject=subject,
            message=message,
            from_email="from@example.com",
            recipient_list=[recipient_email],
            fail_silently=True,
        )


class CommentUpdateView(CommentMixinView, UpdateView):

    form_class = CommentForm


class CommentDeleteView(CommentMixinView, DeleteView):

    ...
