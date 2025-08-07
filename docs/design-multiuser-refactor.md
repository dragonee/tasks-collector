# Multiuser capability for Tasks Collector

The goal of this feature is to add ability to share content between users, while keeping entries private by default.

# Phases of the project

## 1. Introduce login to application

By default, the access to the whole application is limited by server's Basic Auth password.

This means that the code of the application is not protected by any user/

In order to do that, all views in the application should be protected by the login_required decorator or a similar mechanism.

DO NOT SECURE API ROUTES AT THIS STAGE.

The definition of done of this feature is when:

1. All the non-API routes are protected
2. When navigating to the website, user sees a login screen
3. User cannot access any page when they are not logged in
4. A logged in user has an option to log out in the menu

## 2. Secure all API routes with token-based authentication

This application has two clients:

1. There is a tasks-collector-tools repository, that serves as a CLI access to this application
2. There is the frontend set of views, which can be session-based.
   1. However, there is also API access from the frontend JavaScript code. That means, that some calls will also require having a token passed to the frontend part of the application.

Because of that, a token based authentication (or two separate authentications, such as Session-based for frontend views and token-based for API) would be preferrable.